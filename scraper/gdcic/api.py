# -*- coding: utf-8 -*-
"""gdcic 开放平台 API 调用封装（skypt.gdcic.net）。

广东建设信息网数据开放平台的招投标接口完全开放，无需签名/Token，
可直接 httpx GET 调用。

接口列表：
- 招投标列表: GET /api/openplatform/projectBidding/list
- 招投标详情: GET /api/openplatform/projectBidding/get/{id}
- 项目信息:   GET /api/openplatform/project/getByPrjCode/{projectCode}
"""
import logging
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

# API 基础路径（数据开放平台 API 主机）
_BASE_URL = 'https://skypt.gdcic.net'

# API 路径
_LIST_API = '/api/openplatform/projectBidding/list'
_DETAIL_API = '/api/openplatform/projectBidding/get/{item_id}'
_PROJECT_API = '/api/openplatform/project/getByPrjCode/{project_code}'

# 每页条数（与 gzfcj/ggzyjy 对齐）
_PAGE_SIZE = 20

# 来源页面（开放平台前端 SPA）
_REFERER = 'https://skypt.gdcic.net/openplatform/'


def _get_api(scraper, api_path, params=None):
    """发送 GET 请求到指定 API，返回 JSON dict。

    请求前自动加入限速延迟。响应非 code=0 视为业务异常返回 None。

    Args:
        scraper: GdcicScraper 实例（复用其 httpx session 与限速配置）
        api_path: API 路径（如 /api/openplatform/projectBidding/list）
        params: 查询参数 dict

    Returns:
        dict or None: 接口返回的 JSON，请求失败或业务异常返回 None
    """
    if scraper.session is None:
        scraper._create_session()
    try:
        time.sleep(scraper.get_random_delay())
        url = _BASE_URL + api_path
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json, text/plain, */*',
            'Referer': _REFERER,
        }
        logger.info('[gdcic] GET %s params=%s', api_path, params)
        response = scraper.session.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.warning('[gdcic] API HTTP %d: %s', response.status_code, url)
            return None
        data = response.json()
        # 开放平台统一返回 code=0 表示成功
        if data.get('code') not in (0, '0'):
            logger.warning('[gdcic] API 返回异常: code=%s msg=%s path=%s',
                           data.get('code'), data.get('msg'), api_path)
            return None
        return data
    except Exception as e:
        logger.warning('[gdcic] API GET 异常: %s - %s', api_path, e)
        return None


def fetch_bidding_list(scraper, keyword='', page_num=1, page_size=_PAGE_SIZE):
    """查询招投标列表。

    Args:
        scraper: GdcicScraper 实例
        keyword: 工程名称关键词（模糊搜索，空字符串表示不筛选）
        page_num: 页码（从 1 开始）
        page_size: 每页条数

    Returns:
        dict or None: 包含 total/rows 的 JSON，请求失败返回 None
    """
    params = {
        'projectName': keyword,
        'pageNum': page_num,
        'pageSize': page_size,
        'kaptchaKey': '',
        'flag': 'false',
    }
    return _get_api(scraper, _LIST_API, params=params)


def fetch_bidding_detail(scraper, bidding_id):
    """查询招投标详情，补全列表中为 null 的字段。

    注意：详情 API 响应无 code/msg/data 包装，记录字段直接在顶层，
    因此不走 _get_api 的 code 校验，直接发请求并返回 response.json()。

    Args:
        scraper: GdcicScraper 实例
        bidding_id: 招投标记录 ID（列表项的 id 字段）

    Returns:
        dict or None: 包含完整字段的单条记录（字段在顶层），请求失败返回 None
    """
    if not bidding_id:
        return None
    if scraper.session is None:
        scraper._create_session()
    # 路径参数 URL 编码，避免特殊字符破坏路径
    path = _DETAIL_API.format(item_id=quote(str(bidding_id), safe=''))
    try:
        time.sleep(scraper.get_random_delay())
        url = _BASE_URL + path
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json, text/plain, */*',
            'Referer': _REFERER,
        }
        logger.info('[gdcic] GET %s', path)
        response = scraper.session.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning('[gdcic] API HTTP %d: %s', response.status_code, url)
            return None
        # 详情 API 无 code/msg/data 包装，记录字段直接在顶层，直接返回
        return response.json()
    except Exception as e:
        logger.warning('[gdcic] API GET 异常: %s - %s', path, e)
        return None


def fetch_project_info(scraper, project_code):
    """查询项目信息，补全建设单位/总投资/项目所在地等字段。

    注意：项目信息 API 响应无 code/msg/data 包装，记录字段直接在顶层，
    因此不走 _get_api 的 code 校验，直接发请求并返回 response.json()
    （与 fetch_bidding_detail 实现模式一致）。

    Args:
        scraper: GdcicScraper 实例
        project_code: 项目编号（列表项的 projectCode 字段）

    Returns:
        dict or None: 项目信息（字段在顶层），请求失败返回 None
    """
    if not project_code:
        return None
    if scraper.session is None:
        scraper._create_session()
    # 路径参数 URL 编码，避免特殊字符破坏路径
    path = _PROJECT_API.format(project_code=quote(str(project_code), safe=''))
    try:
        time.sleep(scraper.get_random_delay())
        url = _BASE_URL + path
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json, text/plain, */*',
            'Referer': _REFERER,
        }
        logger.info('[gdcic] GET %s', path)
        response = scraper.session.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning('[gdcic] API HTTP %d: %s', response.status_code, url)
            return None
        # 项目信息 API 无 code/msg/data 包装，记录字段直接在顶层，直接返回
        return response.json()
    except Exception as e:
        logger.warning('[gdcic] API GET 异常: %s - %s', path, e)
        return None
