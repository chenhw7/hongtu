# -*- coding: utf-8 -*-
"""ggzy_national API 封装：列表查询 + 详情查询 + WAF Cookie 管理。

全国公共资源交易平台（www.ggzy.gov.cn）部署阿里云 WAF，裸 HTTP 请求（非浏览器
TLS 指纹）会被强制关闭 TCP 连接。需先用 Playwright 加载页面建立会话取得 Cookie，
再由 httpx 携带 Cookie + 浏览器 UA 调用接口（详见报告 §3.4）。

列表接口（详见 §3.2 实测）：
    POST https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList
    Content-Type: application/x-www-form-urlencoded; charset=UTF-8

详情页为静态 HTML（/b/ 正文页），由 scraper/ggzy_national/detail.py 解析。
"""
import logging
import random
import time

import httpx

from scraper.ggzy_national.parser import parse_record

logger = logging.getLogger(__name__)

_BASE_URL = 'https://www.ggzy.gov.cn'
_LIST_PATH = '/information/pubTradingInfo/getTradList'
# 会话建立入口：交易大厅列表页，加载后触发 WAF 放行并下发 Cookie
_SESSION_URL = f'{_BASE_URL}/deal/dealList.html'
_PAGE_SIZE = 20

# Cookie 刷新间隔（秒），防止频繁启动 Playwright
_MIN_COOKIE_REFRESH_INTERVAL = 300

# 浏览器 UA（与 playwright_utils 一致，保证 httpx 请求与浏览器会话同源）
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


class GgzyNationalApi:
    """全国公共资源交易平台 API 客户端，管理 httpx Client + WAF Cookie。"""

    def __init__(self, cookies_str=''):
        """
        Args:
            cookies_str: 已有的 Cookie 字符串（"name1=val1; name2=val2"），
                         为空时需在首次请求前调用 refresh_cookies()
        """
        self._cookies_str = cookies_str
        self._client = None
        self._last_cookie_time = 0

    # ------------------------------------------------------------------
    # Cookie 管理
    # ------------------------------------------------------------------
    def refresh_cookies(self):
        """使用 Playwright 重新获取 WAF Cookie。

        全国平台 WAF 不依赖单一命名 Cookie（非 JSL），故 wait_for_cookie=None，
        直接加载会话入口页后提取全部 Cookie。

        Returns:
            bool: 刷新成功返回 True，失败返回 False
        """
        from scraper.playwright_utils import extract_cookies_for_domain

        logger.info('[ggzy_national] 使用 Playwright 刷新 WAF Cookie...')
        # 不等待特定 Cookie 名；加载会话入口页即触发 WAF 放行
        cookies_str = extract_cookies_for_domain(
            _SESSION_URL, wait_seconds=5, wait_for_cookie=None, max_wait=15,
        )
        if not cookies_str:
            logger.warning('[ggzy_national] Playwright 未能获取到 Cookie')
            return False

        self._cookies_str = cookies_str
        self._last_cookie_time = time.time()
        # 重建 httpx client 以携带新 Cookie
        self._close_client()
        logger.info('[ggzy_national] WAF Cookie 已刷新（%d 项）',
                    len(cookies_str.split(';')))
        return True

    def ensure_cookies(self):
        """确保 Cookie 存在且未过期，必要时自动刷新。"""
        if not self._cookies_str or (
                time.time() - self._last_cookie_time > _MIN_COOKIE_REFRESH_INTERVAL):
            self.refresh_cookies()

    # ------------------------------------------------------------------
    # HTTP 客户端
    # ------------------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': _BASE_URL,
                'Referer': f'{_BASE_URL}/deal/dealList.html',
                'User-Agent': _UA,
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
    def _post_form(self, path, body, max_retries=3):
        """发送 form-urlencoded POST 请求，带限速、重试与 Cookie 自动回退。

        Args:
            path: API 路径（相对 base_url）
            body: POST 表单字段 dict
            max_retries: 最大重试次数

        Returns:
            dict or None: JSON 响应，失败返回 None
        """
        client = self._get_client()

        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(random.uniform(1, 2))
                logger.info('[ggzy_national] POST %s (attempt %d): %s',
                            path, attempt,
                            {k: v for k, v in body.items() if k != 'FINDTXT'})
                # form-urlencoded：httpx 用 data= 而非 json=
                response = client.post(path, data=body)

                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError:
                        # 响应非 JSON（可能是 WAF 拦截页）
                        logger.warning('[ggzy_national] 响应非 JSON: %s',
                                       response.text[:200])
                        if attempt < max_retries:
                            self.refresh_cookies()
                            time.sleep(random.uniform(3, 5))
                            continue
                        return None

                elif response.status_code in (403, 401, 419, 429, 493):
                    # WAF 拦截或限流，刷新 Cookie 后重试
                    logger.warning('[ggzy_national] HTTP %d，刷新 Cookie 后重试',
                                   response.status_code)
                    if attempt < max_retries:
                        self.refresh_cookies()
                        time.sleep(random.uniform(3, 5))
                        continue
                    return None

                else:
                    body_preview = ''
                    try:
                        body_preview = response.text[:200]
                    except Exception:
                        pass
                    logger.warning('[ggzy_national] HTTP %d: %s body=%s',
                                   response.status_code, path, body_preview)
                    if attempt < max_retries:
                        time.sleep(random.uniform(2, 4))
                        continue
                    return None

            except httpx.ConnectError:
                # WAF 强制关闭 TCP 的典型表现
                logger.warning('[ggzy_national] 连接被关闭 (attempt %d): %s',
                               attempt, path)
                if attempt < max_retries:
                    self.refresh_cookies()
                    backoff = 2 ** attempt
                    time.sleep(backoff)
                    continue
                return None
            except httpx.TimeoutException:
                logger.warning('[ggzy_national] 请求超时 (attempt %d): %s',
                               attempt, path)
            except Exception as e:
                logger.warning('[ggzy_national] 请求异常 (attempt %d): %s - %s',
                               attempt, path, e)

            if attempt < max_retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

        logger.error('[ggzy_national] 请求最终失败: %s', path)
        return None

    # ------------------------------------------------------------------
    # 列表接口
    # ------------------------------------------------------------------
    def fetch_list(self, keyword, page, province='', source_type='1',
                   time_begin='', time_end='', deal_time=''):
        """查询 getTradList 列表接口，返回解析后的 lead 列表。

        Args:
            keyword: 搜索关键词（FINDTXT，空字符串=不按关键词过滤）
            page: 页码（从 1 开始）
            province: 省份过滤（DEAL_PROVINCE，6 位行政区划码，空=全国）
            source_type: 1=交易公告（默认）；2=成交公示
            time_begin: 自定义起始日期 YYYY-MM-DD（空=不限定）
            time_end: 自定义结束日期 YYYY-MM-DD（空=不限定）
            deal_time: 时间快捷档位（01=当天、02=近三天、06=近一月等）

        Returns:
            (leads, has_more): lead 列表与是否还有下一页；
            请求失败返回 (None, False)
        """
        body = {
            'SOURCE_TYPE': str(source_type),
            'PAGENUMBER': str(page),
        }
        if deal_time:
            body['DEAL_TIME'] = deal_time
        if time_begin:
            body['TIMEBEGIN'] = time_begin
        if time_end:
            body['TIMEEND'] = time_end
        if keyword:
            body['FINDTXT'] = keyword
        if province:
            body['DEAL_PROVINCE'] = province

        data = self._post_form(_LIST_PATH, body)
        if data is None:
            return None, False

        # 响应结构：{code, message, data: {records, total, size, current, pages}}
        if str(data.get('code', '')) not in ('200', '0', ''):
            # code 非成功且非缺省
            code = data.get('code')
            if code is not None and int(code) != 200:
                logger.warning('[ggzy_national] 接口返回异常: code=%s msg=%s',
                               code, data.get('message'))
                return None, False

        data_obj = data.get('data') or {}
        records = data_obj.get('records') or []
        if not records:
            return [], False

        leads = [parse_record(rec) for rec in records]
        leads = [lead for lead in leads if lead.get('project_name')]
        if not leads:
            return [], False

        # 是否还有下一页：当前页 < 总页数
        current = data_obj.get('current', page) or page
        pages = data_obj.get('pages', 0) or 0
        has_more = bool(pages and int(current) < int(pages))
        return leads, has_more

    # ------------------------------------------------------------------
    # 详情页
    # ------------------------------------------------------------------
    def fetch_detail_html(self, detail_path):
        """获取 /b/ 详情页 HTML 文本（静态页，httpx 直连即可，复用列表接口的 Cookie 会话）。

        Args:
            detail_path: /b/ 正文页路径（如 /information/deal/html/b/530000/0101/20260721/{id}.html）

        Returns:
            str or None: HTML 文本，请求失败返回 None
        """
        if not detail_path:
            return None
        client = self._get_client()
        for attempt in range(1, 3):
            try:
                time.sleep(random.uniform(1, 2))
                url = detail_path if detail_path.startswith('http') else (
                    _BASE_URL + detail_path if detail_path.startswith('/')
                    else _BASE_URL + '/' + detail_path)
                logger.info('[ggzy_national] GET 详情: %s', detail_path)
                response = client.get(url)
                if response.status_code == 200:
                    return response.text
                if response.status_code in (403, 401, 419, 429, 493):
                    if attempt < 2:
                        self.refresh_cookies()
                        time.sleep(random.uniform(3, 5))
                        continue
                return None
            except httpx.ConnectError:
                if attempt < 2:
                    self.refresh_cookies()
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                logger.warning('[ggzy_national] 详情请求异常: %s', e)
                return None
        return None
