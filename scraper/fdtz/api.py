# -*- coding: utf-8 -*-
"""fdtz API 封装：列表查询 + 详情查询 + JSL Cookie 管理。

发改委平台（tzxm.gd.gov.cn）使用 JSL（加速乐）CDN 防护，需先通过
Playwright 获取 Cookie 后才能调用 JSON API。
"""
import logging
import random
import time

import httpx

from scraper.fdtz.parser import (
    CATEGORY_FLAGS,
    DETAIL_ENDPOINTS,
    DETAIL_ID_PARAMS,
    parse_detail,
    parse_list_item,
)

logger = logging.getLogger(__name__)

_BASE_URL = 'https://tzxm.gd.gov.cn'
_API_BASE = '/tzxmspweb/api/publicityInformation'
_PAGE_SIZE = 15

# Cookie 刷新间隔（秒），防止频繁启动 Playwright（JSL Cookie 通常有效期数十分钟）
_MIN_COOKIE_REFRESH_INTERVAL = 300


class FdtzApi:
    """发改委平台 API 客户端，管理 httpx Client + JSL Cookie。"""

    def __init__(self, cookies_str=''):
        """
        Args:
            cookies_str: 已有的 JSL Cookie 字符串（"name1=val1; name2=val2"），
                         为空时需在首次请求前调用 refresh_cookies()
        """
        self._cookies_str = cookies_str
        self._client = None
        self._last_cookie_time = 0

    # ------------------------------------------------------------------
    # Cookie 管理
    # ------------------------------------------------------------------
    def refresh_cookies(self):
        """使用 Playwright 重新获取 JSL Cookie。

        Returns:
            bool: 刷新成功返回 True，失败返回 False
        """
        from scraper.playwright_utils import extract_cookies_for_domain

        logger.info('[fdtz] 使用 Playwright 刷新 JSL Cookie...')
        cookies_str = extract_cookies_for_domain(_BASE_URL, wait_seconds=5)
        if not cookies_str:
            logger.warning('[fdtz] Playwright 未能获取到 Cookie')
            return False

        self._cookies_str = cookies_str
        self._last_cookie_time = time.time()

        # 重建 httpx client 以携带新 Cookie
        self._close_client()
        logger.info('[fdtz] JSL Cookie 已刷新')
        return True

    def ensure_cookies(self):
        """确保 Cookie 存在且未过期，必要时自动刷新。"""
        if not self._cookies_str or (time.time() - self._last_cookie_time > _MIN_COOKIE_REFRESH_INTERVAL):
            self.refresh_cookies()

    # ------------------------------------------------------------------
    # HTTP 客户端
    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Content-Type': 'application/json',
                'Origin': _BASE_URL,
                'Referer': f'{_BASE_URL}/tzxmspweb/',
                'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/120.0.0.0 Safari/537.36'),
            }
            if self._cookies_str:
                headers['Cookie'] = self._cookies_str

            self._client = httpx.Client(
                base_url=_BASE_URL,
                timeout=httpx.Timeout(30.0, connect=15.0),
                follow_redirects=True,
                headers=headers,
            )
        return self._client

    def _close_client(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def close(self):
        """关闭 HTTP 客户端。"""
        self._close_client()

    # ------------------------------------------------------------------
    # 请求封装
    # ------------------------------------------------------------------
    def _post(self, path, body, max_retries=3):
        """发送 POST 请求，带限速和重试。

        Args:
            path: API 路径（相对于 base_url）
            body: POST JSON 请求体 dict
            max_retries: 最大重试次数

        Returns:
            dict or None: JSON 响应，失败返回 None
        """
        client = self._get_client()

        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(random.uniform(1, 2))
                logger.info('[fdtz] POST %s (attempt %d): %s',
                            path, attempt, {k: v for k, v in body.items() if k != 'nameOrCode'})
                response = client.post(path, json=body)

                if response.status_code == 200:
                    data = response.json()
                    code = data.get('code')
                    if code is not None and int(code) != 0:
                        logger.warning('[fdtz] API 返回异常: code=%s msg=%s path=%s',
                                       code, data.get('msg'), path)
                        return None
                    return data

                elif response.status_code in (403, 401, 419, 429):
                    # JSL 拦截或限流，尝试刷新 Cookie
                    logger.warning('[fdtz] HTTP %d，尝试刷新 Cookie 后重试', response.status_code)
                    if attempt < max_retries:
                        self.refresh_cookies()
                        time.sleep(random.uniform(3, 5))
                        continue
                    return None

                else:
                    logger.warning('[fdtz] HTTP %d: %s', response.status_code, path)
                    if attempt < max_retries:
                        time.sleep(random.uniform(2, 4))
                        continue
                    return None

            except httpx.TimeoutException:
                logger.warning('[fdtz] 请求超时 (attempt %d): %s', attempt, path)
            except httpx.ConnectError:
                logger.warning('[fdtz] 连接失败 (attempt %d): %s', attempt, path)
            except Exception as e:
                logger.warning('[fdtz] 请求异常 (attempt %d): %s - %s', attempt, path, e)

            if attempt < max_retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

        logger.error('[fdtz] 请求最终失败: %s', path)
        return None

    # ------------------------------------------------------------------
    # 列表接口
    # ------------------------------------------------------------------
    def fetch_list(self, category, flag, page, city='', keyword=''):
        """查询列表接口，返回解析后的 lead 列表。

        Args:
            category: 分类标识（ba/hz_gs/hz_gg/sp_gs/sp_gg/jn）
            flag: 列表接口 flag 值（1=备案公开, 9=核准公示, 10=核准公告, 6=审批公示, 7=审批公告）
            page: 页码（从 1 开始）
            city: 城市筛选（空字符串=全省）
            keyword: 项目名称关键词（空字符串=不筛选）

        Returns:
            (leads, has_more): lead 列表和是否还有下一页的标记；
            请求失败时返回 (None, False)
        """
        # 确定端点
        if category in ('ba',):
            endpoint = 'selectByPageBA'
        elif category in ('hz_gs', 'hz_gg'):
            endpoint = 'selectHzByPage'
        elif category in ('sp_gs', 'sp_gg'):
            endpoint = 'selectByPageSP'
        elif category == 'jn':
            endpoint = 'selectJnscByPage'
        else:
            logger.warning('[fdtz] 未知分类: %s', category)
            return None, False

        path = f'{_API_BASE}/{endpoint}'
        body = {
            'flag': str(flag),
            'nameOrCode': keyword,
            'pageSize': _PAGE_SIZE,
            'city': city,
            'pageNumber': page,
        }

        data = self._post(path, body)
        if data is None:
            return None, False

        # 解析响应结构：通常是 data.rows / data.list / data.data 等
        rows = (data.get('data') or data.get('rows') or data.get('list')
                or data.get('result') or [])
        if isinstance(rows, dict):
            # 可能嵌套在 data.data.rows 里
            rows = rows.get('rows') or rows.get('list') or []

        if not rows:
            return [], False

        leads = []
        for item in rows:
            lead = parse_list_item(item, category)
            if lead.get('project_name'):
                leads.append(lead)

        has_more = len(rows) >= _PAGE_SIZE
        return leads, has_more

    # ------------------------------------------------------------------
    # 详情接口
    # ------------------------------------------------------------------
    def fetch_detail(self, category, item_id):
        """查询详情接口，返回补充字段 dict。

        Args:
            category: 分类标识
            item_id: 项目主键 ID

        Returns:
            dict or None: 补充字段，请求失败返回 None
        """
        endpoint = DETAIL_ENDPOINTS.get(category)
        if not endpoint:
            logger.warning('[fdtz] 分类 %s 无对应详情接口', category)
            return None

        id_param = DETAIL_ID_PARAMS.get(category, 'id')
        path = f'{_API_BASE}/{endpoint}'
        body = {id_param: item_id}

        data = self._post(path, body)
        if data is None:
            return None

        return parse_detail(data, category)
