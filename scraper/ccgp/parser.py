# -*- coding: utf-8 -*-
"""ccgp 列表项解析（搜索结果 + 频道列表）。"""
import logging
import re

from scraper.utils import parse_date
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# "中央公告/地方公告"频道页支持的频道标识
_CHANNEL_NAMES = {'zygg': '中央公告', 'dfgg': '地方公告'}


def parse_search_results(scraper, soup):
    """解析搜索结果列表页。

    中国政府采购网搜索结果结构:
    <ul class="vT-srch-result-list">
        <li>
            <a href="详情链接">项目标题</a>
            <p>采购单位：xxx &nbsp; 招标编号：xxx</p>
            <span>发布日期</span>
        </li>
    </ul>

    Returns:
        list[dict] 线索列表
    """
    leads = []

    # 主要选择器：搜索结果列表
    result_items = soup.select('.vT-srch-result-list-bid li, ul.vT-srch-result-list li')
    if not result_items:
        # 再尝试通用方式
        result_items = soup.find_all('li', class_=re.compile(r'vT.*result'))

    for item in result_items:
        try:
            lead = parse_list_item(item)
            if lead and lead.get('project_name'):
                leads.append(lead)
        except Exception as e:
            logger.debug('[ccgp] 解析列表项失败: %s', e)
            continue

    logger.info('[ccgp] 搜索结果列表页解析到 %d 条结果', len(leads))
    return leads


def parse_list_item(item):
    """解析单条搜索结果。"""
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
        lead['publish_date'] = parse_date(date_str)
    else:
        # 尝试从 span 标签提取日期
        for span in item.find_all('span'):
            span_text = span.get_text(strip=True)
            date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', span_text)
            if date_match:
                lead['publish_date'] = parse_date(date_match.group(1))
                break

    return lead


def parse_channel_list(scraper, soup, channel):
    """解析频道列表页。

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
            lead = parse_channel_item(item, base_url)
            if lead and lead.get('project_name'):
                leads.append(lead)
        except Exception as e:
            logger.debug('[ccgp] 频道列表项解析失败: %s', e)
            continue

    logger.info('[ccgp] 频道「%s」列表页解析到 %d 条结果',
                _CHANNEL_NAMES.get(channel, channel), len(leads))
    return leads


def parse_channel_item(item, base_url):
    """解析频道列表页单条 <li>，提取标题/链接/公告类型/发布时间/地域/采购人。"""
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
        lead['publish_date'] = parse_date(dt_match.group(1))
        lead['publish_time'] = dt_match.group(2)

    region_match = re.search(r'地域[：:]\s*(\S+)', item_text)
    if region_match:
        lead['region'] = region_match.group(1).strip()[:50]

    buyer_match = re.search(r'采购人[：:]\s*(.+)$', item_text)
    if buyer_match:
        lead['buyer_name'] = buyer_match.group(1).strip()[:200]

    return lead
