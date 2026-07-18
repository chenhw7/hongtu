# -*- coding: utf-8 -*-
"""gzfcj 搜索 API 调用封装（广州住建局 AJAX 接口）。

两个接口均为 POST 请求，参数通过 URL query string 传递，响应为 JSON。
- 施工许可证公示: /ysqgk/Api/WebApi/jzgdsgxkxxlb.ashx
- 竣工验收备案:   /ysqgk/Api/WebApi/gcjgysxxlb.ashx
"""
import logging
import time

logger = logging.getLogger(__name__)

# API 基础路径
_BASE_URL = 'https://zfcj.gz.gov.cn'

# 施工许可证公示接口
_PERMIT_API = '/ysqgk/Api/WebApi/jzgdsgxkxxlb.ashx'
# 竣工验收备案接口
_ACCEPTANCE_API = '/ysqgk/Api/WebApi/gcjgysxxlb.ashx'

# 每页条数
_PAGE_SIZE = 20

# 两个页面的 Referer
_PERMIT_REFERER = 'https://zfcj.gz.gov.cn/zfcj/gczlaq/constructionPermitInformation'
_ACCEPTANCE_REFERER = 'https://zfcj.gz.gov.cn/zfcj/gczlaq/completionAcceptance'


def _post_api(scraper, api_path, params, referer):
    """发送 POST 请求到指定 API，返回 JSON dict。

    请求前自动加入限速延迟。参数通过 URL query string 传递（与前端 JS 行为一致）。

    Args:
        scraper: GzfcjScraper 实例
        api_path: API 路径（如 /ysqgk/Api/WebApi/jzgdsgxkxxlb.ashx）
        params: 查询参数 dict
        referer: 来源页面 URL

    Returns:
        dict or None: 接口返回的 JSON，请求失败返回 None
    """
    if scraper.session is None:
        scraper._create_session()
    try:
        time.sleep(scraper.get_random_delay())
        url = _BASE_URL + api_path
        headers = {
            'User-Agent': scraper.get_random_ua(),
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': referer,
        }
        logger.info('[gzfcj] POST %s params=%s', api_path, params)
        response = scraper.session.post(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.warning('[gzfcj] API HTTP %d: %s', response.status_code, url)
            return None
        return response.json()
    except Exception as e:
        logger.warning('[gzfcj] API POST 异常: %s - %s', api_path, e)
        return None


def fetch_permit_page(scraper, keyword='', page=1):
    """采集施工许可证公示列表。

    Args:
        scraper: GzfcjScraper 实例
        keyword: 工程名称关键词（空字符串表示不筛选）
        page: 页码

    Returns:
        dict or None: 包含 currentPage/totalPage/totalNum/data 的 JSON
    """
    params = {
        'gcmc': keyword,
        'jsdw': '',
        'sgdw': '',
        'sgxkzh': '',
        'page': page,
        'pageSize': _PAGE_SIZE,
    }
    return _post_api(scraper, _PERMIT_API, params, _PERMIT_REFERER)


def fetch_acceptance_page(scraper, keyword='', page=1):
    """采集竣工验收备案列表。

    Args:
        scraper: GzfcjScraper 实例
        keyword: 工程名称关键词（空字符串表示不筛选）
        page: 页码

    Returns:
        dict or None: 包含 currentPage/totalPage/totalNum/data 的 JSON
    """
    params = {
        'gcmc': keyword,
        'jsdw': '',
        'sgdw': '',
        'babh': '',
        'page': page,
        'pageSize': _PAGE_SIZE,
    }
    return _post_api(scraper, _ACCEPTANCE_API, params, _ACCEPTANCE_REFERER)
