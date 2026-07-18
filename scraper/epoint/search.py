# -*- coding: utf-8 -*-
"""EpointWebBuilder ES 搜索 API 通用调用封装。

三省共用同一个 Elasticsearch getFullTextDataNew 接口，仅 base_url / 分类编码 /
时间字段名等参数不同。本模块通过 scraper 实例属性读取这些差异参数。
"""
import json
import logging
import time
from datetime import datetime, timedelta

from scraper.epoint.parser import parse_record

logger = logging.getLogger(__name__)

# API 路径（相对于 base_url）
_API_PATH = '/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew'

# 默认搜索天数
_DEFAULT_DAYS = 30


def _build_search_body(keyword, page, scraper):
    """构建 ES 搜索 POST JSON 请求体。

    Args:
        keyword: 搜索关键词（空字符串表示不按关键词过滤）
        page: 页码，从 1 开始
        scraper: EpointBaseScraper 实例（读取 CATEGORY_NUM / TIME_FIELD 等）

    Returns:
        dict: POST 请求体
    """
    page_size = scraper.PAGE_SIZE
    end_time = datetime.now()
    start_time = end_time - timedelta(days=_DEFAULT_DAYS)

    body = {
        'pn': (page - 1) * page_size,          # 起始行（0-based）
        'rn': str(page_size),                   # 每页记录数（字符串）
        'sort': json.dumps({scraper.TIME_FIELD: '0'}),  # 时间降序
        'condition': [],
        'time': [{
            'fieldName': scraper.TIME_FIELD,
            'startTime': start_time.strftime('%Y-%m-%d'),
            'endTime': end_time.strftime('%Y-%m-%d'),
        }],
        'wd': keyword or '',
        'fields': '',
        'cnum': scraper.CATEGORY_NUM,
        'isBusiness': '1',
    }

    # 按分类编码过滤
    if scraper.CATEGORY_NUM:
        body['condition'].append({
            'field': 'categorynum',
            'value': scraper.CATEGORY_NUM,
            'likeType': 2,
        })

    return body


def _post_search(scraper, body):
    """发送 ES 搜索 POST 请求，返回解析后的 JSON dict。

    使用 scraper.session.post() 直接发送，请求前加入限速延迟。

    Args:
        scraper: EpointBaseScraper 实例
        body: POST 请求体 dict

    Returns:
        dict or None: 接口返回的 JSON，请求失败返回 None
    """
    if scraper.session is None:
        scraper._create_session()

    api_url = scraper.base_url.rstrip('/') + _API_PATH
    try:
        time.sleep(scraper.get_random_delay())
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json',
        }
        referer = scraper.get_random_referer()
        if referer:
            headers['Referer'] = referer

        logger.info('[%s] POST 搜索: pn=%s wd=%s',
                    scraper.source_type, body.get('pn'), body.get('wd', ''))
        response = scraper.session.post(api_url, json=body, headers=headers)
        if response.status_code != 200:
            logger.warning('[%s] 搜索接口 HTTP %d: %s',
                           scraper.source_type, response.status_code, api_url)
            return None
        return response.json()
    except Exception as e:
        logger.warning('[%s] 搜索 POST 异常: %s - %s',
                       scraper.source_type, api_url, e)
        return None


def _process_page(scraper, payload):
    """处理 ES 搜索接口返回的 JSON，解析为 Lead 列表。

    Args:
        scraper: EpointBaseScraper 实例
        payload: 接口返回的 JSON dict

    Returns:
        list[dict] or None or []: 线索列表；None 表示异常应停止该关键词；
        [] 表示该页无更多结果
    """
    if payload is None:
        return None

    result = payload.get('result') or {}
    total_count = result.get('totalcount', 0)
    records = result.get('records') or []

    if not records:
        return []

    leads = []
    for record in records:
        lead = parse_record(record, scraper)
        if lead and lead.get('project_name'):
            leads.append(lead)

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

        # 请求详情页（SSR HTML）
        detail_url = lead.pop('_detail_path', '')
        if detail_url:
            from scraper.epoint.detail import fetch_detail
            detail_data = fetch_detail(scraper, detail_url)
            if detail_data:
                lead.update(detail_data)
        detailed_leads.append(lead)

    if skipped:
        logger.info('[%s] 跳过 %d 条已存在项的详情请求', scraper.source_type, skipped)

    return detailed_leads


def search_page(scraper, keyword, page):
    """按关键词搜索并采集单页。

    Args:
        scraper: EpointBaseScraper 实例
        keyword: 搜索关键词
        page: 页码

    Returns:
        list[dict] 线索列表，None 表示请求失败
    """
    body = _build_search_body(keyword, page, scraper)
    payload = _post_search(scraper, body)
    return _process_page(scraper, payload)
