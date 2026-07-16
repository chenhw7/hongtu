# -*- coding: utf-8 -*-
"""ccgp 关键词搜索采集。"""
import logging

from scraper.utils import parse_date

logger = logging.getLogger(__name__)


def build_search_url(keyword, page, zone_id=None):
    """构建搜索 URL 和参数。

    Args:
        keyword: 搜索关键词
        page: 页码
        zone_id: 省份 zoneId（可选，用于分省过滤）
    """
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
        'zoneId': zone_id or '',
    }
    return 'http://search.ccgp.gov.cn/bxsearch', params


def scrape_search_page(scraper, keyword, page, zone_id=None):
    """按关键词搜索并采集单页。

    Args:
        scraper: CcgpScraper 实例
        keyword: 搜索关键词
        page: 页码
        zone_id: 省份 zoneId（可选）

    Returns:
        list[dict] 线索列表，None 表示请求失败
    """
    from scraper.ccgp.parser import parse_search_results, parse_list_item

    url, params = build_search_url(keyword, page, zone_id=zone_id)
    soup = scraper.fetch_soup(url, params=params)
    if soup is None:
        return None

    # 检查是否被反爬拦截
    page_text = soup.get_text()
    if '访问过于频繁' in page_text or '请稍后再试' in page_text:
        logger.warning('[ccgp] 检测到反爬提示，停止采集')
        return None

    # 解析搜索结果列表
    leads = parse_search_results(scraper, soup)
    if leads is None:
        return []

    # 逐条访问详情页补充信息
    detailed_leads = []
    for lead in leads:
        detail_url = lead.get('source_url', '')
        if detail_url:
            detail_data = scraper._fetch_detail(detail_url)
            if detail_data:
                lead.update(detail_data)
        detailed_leads.append(lead)

    return detailed_leads
