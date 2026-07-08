# -*- coding: utf-8 -*-
"""中国政府采购网爬虫 (ccgp.gov.cn)"""
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class CcgpScraper(BaseScraper):
    """中国政府采购网爬虫

    搜索URL: http://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index={page}&kw={keyword}
    """

    source_type = 'ccgp'
    base_url = 'http://search.ccgp.gov.cn/bxsearch'
    referer = 'http://www.ccgp.gov.cn/'

    def _build_search_url(self, keyword, page):
        """构建搜索URL和参数"""
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=365)
        params = {
            'searchtype': '1',
            'page_index': str(page),
            'bidSort': '0',
            'pinMu': '0',
            'bidType': '0',
            'kw': keyword,
            'start_time': start_date.strftime('%Y:%m:%d'),
            'end_time': end_date.strftime('%Y:%m:%d'),
            'timeType': '6',
            'pppStatus': '0',
            'dbselect': 'bidx',
            'displayZone': '',
            'zoneId': '',
        }
        return self.base_url, params

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict] 线索列表，None 表示请求失败
        """
        url, params = self._build_search_url(keyword, page)
        soup = self.fetch_soup(url, params=params)
        if soup is None:
            return None

        # 检查是否被反爬拦截
        page_text = soup.get_text()
        if '访问过于频繁' in page_text or '请稍后再试' in page_text:
            logger.warning('[ccgp] 检测到反爬提示，停止采集')
            return None

        # 解析搜索结果列表
        leads = self.parse(soup)
        if leads is None:
            return []

        # 逐条访问详情页补充信息
        detailed_leads = []
        for lead in leads:
            detail_url = lead.get('source_url', '')
            if detail_url:
                detail_data = self._fetch_detail(detail_url)
                if detail_data:
                    lead.update(detail_data)
            detailed_leads.append(lead)

        return detailed_leads

    def parse(self, soup):
        """解析搜索结果列表页

        中国政府采购网搜索结果结构:
        <ul class="vT-srch-result-list">
            <li>
                <a href="详情链接">项目标题</a>
                <p>采购单位：xxx &nbsp; 招标编号：xxx</p>
                <span>发布日期</span>
            </li>
        </ul>
        """
        leads = []

        # 主要选择器：搜索结果列表
        result_items = soup.select('.vT-srch-result-list-bid li, ul.vT-srch-result-list li')
        if not result_items:
            # 再尝试通用方式
            result_items = soup.find_all('li', class_=re.compile(r'vT.*result'))

        for item in result_items:
            try:
                lead = self._parse_list_item(item)
                if lead and lead.get('project_name'):
                    leads.append(lead)
            except Exception as e:
                logger.debug('[ccgp] 解析列表项失败: %s', e)
                continue

        logger.info('[ccgp] 列表页解析到 %d 条结果', len(leads))
        return leads

    def _parse_list_item(self, item):
        """解析单条搜索结果"""
        lead = {}

        # 提取标题和链接
        link = item.find('a')
        if link:
            lead['project_name'] = link.get_text(strip=True)
            href = link.get('href', '')
            if href and not href.startswith('http'):
                href = 'http://www.ccgp.gov.cn' + href
            lead['source_url'] = href

        # 提取采购单位、招标编号等文本信息
        text_parts = []
        for p in item.find_all('p'):
            text_parts.append(p.get_text(strip=True))
        full_text = ' '.join(text_parts)

        # 解析采购单位
        buyer_match = re.search(r'采购单位[：:]\s*(.+?)(?:\s|$|&)', full_text)
        if buyer_match:
            lead['buyer_name'] = buyer_match.group(1).strip()

        # 解析招标编号
        bid_match = re.search(r'(?:招标编号|项目编号|公告编号)[：:]\s*([A-Za-z0-9\-_/]+)', full_text)
        if bid_match:
            lead['bidding_number'] = bid_match.group(1).strip()

        # 解析发布日期
        date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', full_text)
        if date_match:
            date_str = date_match.group(1)
            lead['publish_date'] = self._parse_date(date_str)
        else:
            # 尝试从 span 标签提取日期
            for span in item.find_all('span'):
                span_text = span.get_text(strip=True)
                date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', span_text)
                if date_match:
                    lead['publish_date'] = self._parse_date(date_match.group(1))
                    break

        return lead

    def _fetch_detail(self, url):
        """获取详情页并解析补充信息

        Returns:
            dict: 补充字段（联系人、电话、预算、截止日期等）
        """
        soup = self.fetch_soup(url)
        if soup is None:
            return {}

        try:
            return self._parse_detail(soup)
        except Exception as e:
            logger.debug('[ccgp] 详情页解析失败 %s: %s', url, e)
            return {}

    def _parse_detail(self, soup):
        """解析详情页，提取更完整的信息

        政府采购公告详情页通常包含表格或段落，
        含有联系人、电话、预算金额、投标截止时间等。
        """
        detail = {}

        # 获取全文文本用于正则匹配
        full_text = soup.get_text(separator='\n', strip=True)

        # 提取联系人
        contact_patterns = [
            r'联系人[（(]采购人[)）][：:]\s*(.+?)(?:\n|$)',
            r'采购人联系人[：:]\s*(.+?)(?:\n|$)',
            r'联\s*系\s*人[：:]\s*(.+?)(?:\n|$|,|，|电)',
            r'项目联系人[：:]\s*(.+?)(?:\n|$)',
        ]
        for pattern in contact_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['contact_person'] = match.group(1).strip()[:50]
                break

        # 提取电话
        phone_patterns = [
            r'联系电话[（(]采购人[)）][：:]\s*([\d\-（）\(\)\s]+)',
            r'采购人电话[：:]\s*([\d\-（）\(\)\s]+)',
            r'联\s*系\s*电\s*话[：:]\s*([\d\-（）\(\)\s]+)',
            r'电\s*话[：:]\s*([\d\-（）\(\)\s]+)',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['phone'] = match.group(1).strip()[:50]
                break

        # 提取预算金额
        budget_patterns = [
            r'预算金额[：:]\s*([\d,.]+)\s*(万元|元)',
            r'项目预算[：:]\s*([\d,.]+)\s*(万元|元)',
            r'采购预算[：:]\s*([\d,.]+)\s*(万元|元)',
            r'预算总金额[：:]\s*([\d,.]+)\s*(万元|元)',
        ]
        for pattern in budget_patterns:
            match = re.search(pattern, full_text)
            if match:
                amount_str = match.group(1).replace(',', '').strip()
                try:
                    amount = float(amount_str)
                    # 判断单位：万元则转换为元
                    if match.group(2) == '万元':
                        amount = amount * 10000
                    detail['budget_amount'] = amount
                except ValueError:
                    pass
                break

        # 提取投标截止日期
        deadline_patterns = [
            r'(?:投标|响应|递交|提交)[^。\n]*?截止[^\n]*?(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
            r'截止时间[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
            r'开标时间[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
        ]
        for pattern in deadline_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['deadline'] = self._parse_date(match.group(1))
                break

        # 尝试从详情页补充招标编号
        if not detail.get('bidding_number'):
            bid_patterns = [
                r'(?:招标编号|项目编号|公告编号|采购编号)[：:]\s*([A-Za-z0-9\-_/]+)',
            ]
            for pattern in bid_patterns:
                match = re.search(pattern, full_text)
                if match:
                    detail['bidding_number'] = match.group(1).strip()
                    break

        # 尝试补充采购单位
        if not detail.get('buyer_name'):
            buyer_patterns = [
                r'采购单位[：:]\s*(.+?)(?:\n|$|地)',
                r'采购人[：:]\s*(.+?)(?:\n|$|地)',
            ]
            for pattern in buyer_patterns:
                match = re.search(pattern, full_text)
                if match:
                    detail['buyer_name'] = match.group(1).strip()[:200]
                    break

        return detail

    @staticmethod
    def _parse_date(date_str):
        """解析日期字符串，返回 date 对象"""
        try:
            # 清理中文日期
            date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
            date_str = date_str.replace('/', '-').strip()
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None
