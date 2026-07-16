# -*- coding: utf-8 -*-
"""ccgp 频道列表采集（中央公告 / 地方公告）。

支持格式：
- channel:zygg              → 中央公告
- channel:dfgg              → 地方公告（混合，保留兼容）
- channel:dfgg:guangdong    → 广东省地方公告（分省，新增）
"""
import logging

from scraper.ccgp.regions import REGIONS

logger = logging.getLogger(__name__)

# "中央公告/地方公告"频道页支持的频道标识
_CHANNEL_NAMES = {'zygg': '中央公告', 'dfgg': '地方公告'}


def build_channel_url(channel, page, region_code=None):
    """构建频道列表页 URL，page 从 1 开始（1 对应频道首页，之后为 index_{page-1}.htm）。

    分省频道直接使用带 zoneId 的搜索接口（ccgp 频道页本身不支持按省份过滤 URL）。
    """
    base = 'http://www.ccgp.gov.cn/cggg/%s/' % channel
    if page <= 1:
        return base
    return '%sindex_%d.htm' % (base, page - 1)


def build_province_channel_url(keyword, page):
    """为分省频道构建搜索 URL。

    分省频道（channel:dfgg:<region_code>）底层使用搜索接口 + zoneId 过滤，
    等价于对该省做一次不限关键词的招标信息搜索。
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
        'kw': '',
        'start_time': start_date.strftime('%Y:%m:%d'),
        'end_time': end_date.strftime('%Y:%m:%d'),
        'timeType': '6',
        'pppStatus': '0',
        'dbselect': 'bidx',
        'displayZone': '',
        'zoneId': keyword,  # zoneId 作为搜索过滤
    }
    return 'http://search.ccgp.gov.cn/bxsearch', params


def scrape_channel_page(scraper, channel, page, region_code=None):
    """采集"中央公告/地方公告"频道的某一页列表，并补充详情页信息。

    Args:
        scraper: CcgpScraper 实例
        channel: 'zygg' 或 'dfgg'
        page: 页码（从 1 开始）
        region_code: 省份代码（如 'guangdong'），为 None 时采集全国混合列表

    Returns:
        list[dict] 线索列表，None 表示请求失败
    """
    from scraper.ccgp.parser import parse_channel_list, parse_channel_item, parse_search_results

    # 分省频道使用搜索接口 + zoneId 过滤（频道页本身不支持按省份过滤）
    if region_code:
        region = REGIONS.get(region_code)
        if region is None:
            logger.error('[ccgp] 无效的地区代码: %s', region_code)
            return None
        zone_id = region['zoneId']
        url, params = build_province_channel_url(zone_id, page)
        soup = scraper.fetch_soup(url, params=params)
        if soup is None:
            return None

        page_text = soup.get_text()
        if '访问过于频繁' in page_text or '请稍后再试' in page_text:
            logger.warning('[ccgp] 检测到反爬提示，停止采集')
            return None

        leads = parse_search_results(scraper, soup)
        # 分省频道：从 region_code 参数直接赋值 region（搜索结果 HTML 不含地域信息）
        region_name = region['name']
        for lead in leads:
            lead.setdefault('region', region_name)
    else:
        url = build_channel_url(channel, page)
        soup = scraper.fetch_soup(url)
        if soup is None:
            return None
        leads = parse_channel_list(scraper, soup, channel)

    if not leads:
        return []

    # 逐条访问详情页补充信息（已存在的项先批量跳过，避免重复请求详情）
    existing_keys = scraper._prefetch_existing_keys(leads)
    detailed_leads = []
    skipped = 0
    for lead in leads:
        scraper._check_pause_and_stop()
        key = scraper._lead_dedup_key(lead)
        if key and key in existing_keys:
            skipped += 1
            detailed_leads.append(lead)  # 保留列表页字段，不请求详情
            continue
        detail_url = lead.get('source_url', '')
        if detail_url:
            detail_data = scraper._fetch_detail(detail_url)
            if detail_data:
                lead.update(detail_data)
        detailed_leads.append(lead)
    if skipped:
        logger.info('[ccgp] 跳过 %d 条已存在项的详情请求', skipped)

    return detailed_leads
