# -*- coding: utf-8 -*-
"""ggzyjy 搜索 API 调用 + 分页逻辑（POST JSON 请求）。"""
import logging
import time
from datetime import datetime, timedelta

from scraper.ggzyjy.regions import PROVINCE_SITE_CODE
from scraper.ggzyjy.parser import parse_item

logger = logging.getLogger(__name__)

_SEARCH_URL = 'https://ygp.gdzwfw.gov.cn/ggzy-portal/search/v2/items'
_PAGE_SIZE = 20


def _build_search_body(keyword, page, site_code=None, trading_type_code=None,
                       notice_second_type=None, days=30):
    """构建搜索 POST 请求体。

    Args:
        keyword: 搜索关键词（空字符串表示不按关键词过滤）
        page: 页码，从 1 开始
        site_code: 地区编码，默认省级 440000
        trading_type_code: 交易类型编码（如 "jsgc"=工程建设）
        notice_second_type: 公告二级类型（"A"=工程建设, "D"=政府采购）
        days: 搜索最近天数

    Returns:
        dict: POST 请求体
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    body = {
        'pageNo': page,
        'pageSize': _PAGE_SIZE,
        'siteCode': site_code or PROVINCE_SITE_CODE,
        'startTime': start_time.strftime('%Y%m%d000000'),
        'endTime': end_time.strftime('%Y%m%d235959'),
    }
    if keyword:
        body['keyword'] = keyword
    if trading_type_code:
        body['tradingTypeCode'] = trading_type_code
    if notice_second_type:
        body['noticeSecondType'] = notice_second_type
    return body


def _post_search(scraper, body):
    """发送搜索 POST 请求，返回解析后的 JSON dict。

    使用 scraper.session.post() 直接发送，请求前加入限速延迟。

    Args:
        scraper: GgzyjyScraper 实例
        body: POST 请求体 dict

    Returns:
        dict or None: 接口返回的 JSON，请求失败返回 None
    """
    if scraper.session is None:
        scraper._create_session()
    try:
        time.sleep(scraper.get_random_delay())
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        if scraper.referer:
            headers['Referer'] = scraper.referer
        logger.info('[ggzyjy] POST 搜索: pageNo=%s keyword=%s',
                    body.get('pageNo'), body.get('keyword', ''))
        response = scraper.session.post(_SEARCH_URL, json=body, headers=headers)
        if response.status_code != 200:
            logger.warning('[ggzyjy] 搜索接口 HTTP %d: %s', response.status_code, _SEARCH_URL)
            return None
        return response.json()
    except Exception as e:
        logger.warning('[ggzyjy] 搜索 POST 异常: %s - %s', _SEARCH_URL, e)
        return None


def _process_page(scraper, payload):
    """处理搜索接口返回的 JSON，解析 lead 列表并请求详情。

    Args:
        scraper: GgzyjyScraper 实例
        payload: 搜索接口返回的 JSON dict

    Returns:
        list[dict] or None or []: 线索列表；None 表示异常应停止该关键词；
        [] 表示该页无更多结果
    """
    if payload is None:
        return None

    errcode = payload.get('errcode')
    if errcode is not None and errcode != 0:
        logger.warning('[ggzyjy] 搜索接口返回异常: errcode=%s errmsg=%s',
                       errcode, payload.get('errmsg'))
        return None

    data = payload.get('data') or {}
    page_data = data.get('pageData') or []
    if not page_data:
        return []

    # 检查是否已超出总页数
    page_no = data.get('pageNo', 1)
    page_total = data.get('pageTotal', 0)
    if isinstance(page_total, int) and page_no > page_total:
        return []

    # 解析列表项
    leads = [parse_item(item) for item in page_data]
    leads = [lead for lead in leads if lead.get('project_name')]

    if not leads:
        return []

    # 前置去重：跳过已存在项的详情请求
    existing_keys = scraper._prefetch_existing_keys(leads)
    detailed_leads = []
    skipped = 0
    for lead in leads:
        scraper._check_pause_and_stop()
        key = scraper._lead_dedup_key(lead)
        if key and key in existing_keys:
            skipped += 1
            detailed_leads.append(lead)
            continue
        # 请求详情
        notice_id = lead.pop('_notice_id', '')
        project_code = lead.pop('_project_code', '')
        site_code = lead.pop('_site_code', '')
        trading_type = lead.pop('_trading_type', 'A')
        if notice_id:
            from scraper.ggzyjy.detail import fetch_detail
            detail_data = fetch_detail(scraper, notice_id, project_code,
                                       site_code, trading_type)
            if detail_data:
                lead.update(detail_data)
        detailed_leads.append(lead)
    if skipped:
        logger.info('[ggzyjy] 跳过 %d 条已存在项的详情请求', skipped)

    return detailed_leads


def scrape_search_page(scraper, keyword, page):
    """按关键词搜索并采集单页（全省范围）。

    Args:
        scraper: GgzyjyScraper 实例
        keyword: 搜索关键词
        page: 页码

    Returns:
        list[dict] 线索列表，None 表示请求失败
    """
    body = _build_search_body(keyword, page)
    payload = _post_search(scraper, body)
    return _process_page(scraper, payload)


def scrape_channel_page(scraper, channel, page, region_code=None):
    """频道列表浏览采集（不带关键词，按交易类型浏览）。

    伪关键词格式：
        channel:jsgc            — 工程建设（全省）
        channel:zfcg            — 政府采购（全省）
        channel:jsgc:guangzhou  — 工程建设（广州市）

    Args:
        scraper: GgzyjyScraper 实例
        channel: 频道标识 ("jsgc"=工程建设, "zfcg"=政府采购)
        page: 页码
        region_code: 地区代码（regions.py 中的 key，如 "guangzhou"）

    Returns:
        list[dict] 线索列表，None 表示请求失败
    """
    from scraper.ggzyjy.regions import REGIONS

    # 确定交易类型参数
    if channel == 'zfcg':
        trading_type_code = None
        notice_second_type = 'D'
    else:
        # 默认工程建设
        trading_type_code = 'jsgc'
        notice_second_type = 'A'

    # 确定地区编码
    site_code = PROVINCE_SITE_CODE
    if region_code:
        region_info = REGIONS.get(region_code)
        if region_info:
            site_code = region_info['siteCode']

    body = _build_search_body('', page, site_code=site_code,
                              trading_type_code=trading_type_code,
                              notice_second_type=notice_second_type)
    payload = _post_search(scraper, body)
    return _process_page(scraper, payload)
