# -*- coding: utf-8 -*-
"""中国政府采购网爬虫 (ccgp.gov.cn)"""
import logging
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# 详情页中常见的附件文件扩展名
_ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|docx?|xlsx?|zip|rar|7z|txt)(\?.*)?$', re.IGNORECASE)

# 详情页固定分段的边界关键词（用于从某分段标题截取到下一分段之前的文本）
_SECTION_BOUNDARY_RE = re.compile(
    r'(采购人信息|采购代理机构信息|项目联系方式|相关附件|评审专家|代理服务收费|公告期限|其他补充事宜|主办单位)'
)

# “中央公告/地方公告”频道页支持的频道标识
_CHANNEL_NAMES = {'zygg': '中央公告', 'dfgg': '地方公告'}
# 采集配置里用 'channel:zygg' / 'channel:dfgg' 这种伪关键词表示按频道采集（而非关键词搜索）
_CHANNEL_KEYWORD_RE = re.compile(r'^channel:(zygg|dfgg)$')


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
            keyword: 搜索关键词，若形如 'channel:zygg'/'channel:dfgg' 则改为按
                     中央公告/地方公告频道列表采集（详见 _scrape_channel_page）
            page: 页码

        Returns:
            list[dict] 线索列表，None 表示请求失败
        """
        channel_match = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if channel_match:
            return self._scrape_channel_page(channel_match.group(1), page)

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

    # ------------------------------------------------------------------
    # “中央公告/地方公告”频道列表页采集
    #
    # 与关键词搜索（search.ccgp.gov.cn）不同，www.ccgp.gov.cn/cggg/{zygg|dfgg}/
    # 是按频道分页的全量公告列表，列表本身已直接给出"公告类型"（中标/更正/终止/
    # 成交/竞争性磋商/公开招标/其他公告等）和"地域"，无需依赖详情页正则猜测，
    # 准确率更高，也不受限于关键词覆盖面。
    # ------------------------------------------------------------------
    @staticmethod
    def _build_channel_url(channel, page):
        """构建频道列表页URL，page 从 1 开始（1对应频道首页，之后为 index_{page-1}.htm）"""
        base = 'http://www.ccgp.gov.cn/cggg/%s/' % channel
        if page <= 1:
            return base
        return '%sindex_%d.htm' % (base, page - 1)

    def _scrape_channel_page(self, channel, page):
        """采集"中央公告/地方公告"频道的某一页列表，并补充详情页信息

        Args:
            channel: 'zygg' 或 'dfgg'
            page: 页码（从1开始）

        Returns:
            list[dict] 线索列表，None 表示请求失败
        """
        url = self._build_channel_url(channel, page)
        soup = self.fetch_soup(url)
        if soup is None:
            return None

        leads = self._parse_channel_list(soup, channel)
        if not leads:
            return []

        detailed_leads = []
        for lead in leads:
            detail_url = lead.get('source_url', '')
            if detail_url:
                detail_data = self._fetch_detail(detail_url)
                if detail_data:
                    lead.update(detail_data)
            detailed_leads.append(lead)

        return detailed_leads

    def _parse_channel_list(self, soup, channel):
        """解析频道列表页

        固定结构：
        <ul class="c_list_bid">
            <li>
                <a href="./gzgg/202607/xxx.htm" title="完整标题">标题（可能被截断）</a>
                <em rel="bxlx">公告类型</em> 发布时间：<em>YYYY-MM-DD HH:MM</em>
                地域：<em>省份</em> 采购人：<em>采购单位</em>
            </li>
        </ul>
        """
        leads = []
        base_url = 'http://www.ccgp.gov.cn/cggg/%s/' % channel
        items = soup.select('ul.c_list_bid li')

        for item in items:
            try:
                lead = self._parse_channel_item(item, base_url)
                if lead and lead.get('project_name'):
                    leads.append(lead)
            except Exception as e:
                logger.debug('[ccgp] 频道列表项解析失败: %s', e)
                continue

        logger.info('[ccgp] 频道「%s」列表页解析到 %d 条结果',
                    _CHANNEL_NAMES.get(channel, channel), len(leads))
        return leads

    @staticmethod
    def _parse_channel_item(item, base_url):
        """解析频道列表页单条 <li>，提取标题/链接/公告类型/发布时间/地域/采购人"""
        lead = {}

        link = item.find('a')
        if not link:
            return None

        title = (link.get('title') or link.get_text(strip=True)).strip()
        if not title:
            return None
        lead['project_name'] = title[:500]

        href = link.get('href', '')
        if href:
            lead['source_url'] = urljoin(base_url, href)

        type_em = item.find('em', attrs={'rel': 'bxlx'})
        if type_em:
            announcement_type = type_em.get_text(strip=True)
            if announcement_type:
                lead['announcement_type'] = announcement_type[:50]

        item_text = item.get_text(' ', strip=True)

        dt_match = re.search(r'发布时间[：:]\s*(\d{4}-\d{1,2}-\d{1,2})\s+(\d{1,2}:\d{2})', item_text)
        if dt_match:
            lead['publish_date'] = CcgpScraper._parse_date(dt_match.group(1))
            lead['publish_time'] = dt_match.group(2)

        region_match = re.search(r'地域[：:]\s*(\S+)', item_text)
        if region_match:
            lead['region'] = region_match.group(1).strip()[:50]

        buyer_match = re.search(r'采购人[：:]\s*(.+)$', item_text)
        if buyer_match:
            lead['buyer_name'] = buyer_match.group(1).strip()[:200]

        return lead

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
            dict: 补充字段（联系人、电话、预算、截止日期、附件、原始HTML等）
        """
        html_text, soup = self.fetch_html(url)
        if soup is None:
            return {}

        try:
            detail = self._parse_detail(soup)
            detail['attachments'] = self._extract_attachments(soup, url)
            if html_text:
                detail['_raw_html'] = html_text
            return detail
        except Exception as e:
            logger.debug('[ccgp] 详情页解析失败 %s: %s', url, e)
            return {}

    @staticmethod
    def _extract_attachments(soup, base_url):
        """提取详情页中的附件下载链接（招标文件、报价单等）"""
        attachments = []
        seen_urls = set()
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
            if not _ATTACHMENT_EXT_RE.search(href):
                continue
            full_url = href if href.startswith('http') else urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            name = a.get_text(strip=True) or os.path.basename(urlparse(full_url).path) or 'attachment'
            attachments.append({'name': name[:200], 'url': full_url})
        return attachments

    @staticmethod
    def _extract_section(text, header_pattern):
        """截取从 header_pattern 匹配处到下一个已知分段标题（或文末）之间的文本"""
        m = re.search(header_pattern, text)
        if not m:
            return ''
        rest = text[m.end():]
        next_m = _SECTION_BOUNDARY_RE.search(rest)
        end = next_m.start() if next_m else len(rest)
        return rest[:end]

    @staticmethod
    def _extract_field(section_text, label_pattern):
        """在分段文本中按 '标签：值' 的形式提取字段值（取到该行换行为止）

        label_pattern 用非捕获组包裹，避免其内部的 "|" 分支破坏后面的取值分组。
        """
        m = re.search(r'(?:%s)\s*[：:]\s*(.+)' % label_pattern, section_text)
        if not m:
            return None
        value = m.group(1).split('\n')[0].strip()
        return value or None

    def _parse_detail(self, soup):
        """解析详情页，提取更完整的信息

        ccgp 聚合了全国各省级采购网站的公告，页面模板差异较大。
        解析优先级：
        1. 精确结构化提取——标题下方固定格式的发布时间"YYYY年MM月DD日 HH:MM"，
           以及末尾"1.采购人信息/2.采购代理机构信息/3.项目联系方式"三个固定分段
           （多数公告都遵循该模板，字段边界清晰，准确率高）。
        2. 兼容旧版/非标准页面——找不到固定分段时，退回原有的全文正则兜底匹配。
        """
        detail = {}

        # 获取全文文本用于正则匹配
        full_text = soup.get_text(separator='\n', strip=True)

        # ---- 1) 精确提取发布时间：标题区域固定格式 "YYYY年MM月DD日 HH:MM" ----
        dt_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})', full_text[:600])
        if dt_match:
            y, mo, d, h, mi = dt_match.groups()
            parsed_date = self._parse_date(f'{y}-{mo}-{d}')
            if parsed_date:
                detail['publish_date'] = parsed_date
                detail['publish_time'] = f'{int(h):02d}:{mi}'

        # ---- 2) 分段结构化提取：采购人信息 / 采购代理机构信息 / 项目联系方式 ----
        buyer_section = self._extract_section(full_text, r'采购人信息')
        agency_section = self._extract_section(full_text, r'采购代理机构信息')
        contact_section = self._extract_section(full_text, r'项目联系方式')

        buyer_phone_fallback = None
        if buyer_section:
            name = self._extract_field(buyer_section, r'名\s*称')
            addr = self._extract_field(buyer_section, r'地\s*址')
            tel = self._extract_field(buyer_section, r'联系方式|电\s*话')
            if name:
                detail['buyer_name'] = name[:200]
            if addr:
                detail['buyer_address'] = addr[:300]
            if tel:
                buyer_phone_fallback = tel[:50]

        if agency_section:
            name = self._extract_field(agency_section, r'名\s*称')
            tel = self._extract_field(agency_section, r'联系方式|电\s*话')
            if name:
                detail['agency_name'] = name[:200]
            if tel:
                detail['agency_phone'] = tel[:50]

        if contact_section:
            person = self._extract_field(contact_section, r'项目联系人|联\s*系\s*人')
            tel = self._extract_field(contact_section, r'电\s*话|联系方式')
            if person:
                detail['contact_person'] = person[:50]
            if tel:
                detail['phone'] = tel[:50]

        # 联系电话兜底：优先用"项目联系方式"分段的电话，没有则退回采购人电话
        if not detail.get('phone') and buyer_phone_fallback:
            detail['phone'] = buyer_phone_fallback

        # ---- 3) 兼容旧版页面结构：以下正则仅在结构化提取未命中时兜底 ----
        # 提取联系人
        contact_patterns = [
            r'联系人[（(]采购人[)）][：:]\s*(.+?)(?:\n|$)',
            r'采购人联系人[：:]\s*(.+?)(?:\n|$)',
            r'联\s*系\s*人[：:]\s*(.+?)(?:\n|$|,|，|电)',
            r'项目联系人[：:]\s*(.+?)(?:\n|$)',
        ]
        if not detail.get('contact_person'):
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
        if not detail.get('phone'):
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
