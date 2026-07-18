# -*- coding: utf-8 -*-
"""gdcic Playwright SPA 渲染 + XHR/Fetch 请求拦截。

广东建设信息网（www.gdcic.net）主站为 SSR ASP.NET；
三库一平台（skypt.gdcic.net）和数据开放平台（skypt.gdcic.net/openplatform/）
均为 Vue.js SPA，需要 Playwright 渲染并拦截 XHR 发现后端 API 端点。

优先策略：拦截到 API 后用 httpx 直连，提高吞吐；
降级策略：API 有签名参数无法直调时，保持 Playwright 全流程渲染，从 DOM 提取。
"""
import logging
import random
import time
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# 页面加载超时（毫秒）
_PAGE_TIMEOUT = 30000

# SPA 入口页面（按优先级尝试）
_SPA_ENTRY_URLS = [
    'https://skypt.gdcic.net/openplatform/',   # 数据开放平台（Vue SPA）
    'https://skypt.gdcic.net/',                # 三库一平台
]

# 已知 API 路径模式（拦截到的 XHR 匹配这些模式时视为候选端点）
_API_PATH_PATTERNS = [
    '/api/',
    '/openplatform/',
    '/skypt/',
    '/gdcic/',
    '/queryData',
    '/getList',
    '/getData',
    '/search',
]

# API 拦截排除模式（静态资源 / 埋点 / CDN 等无关请求）
_API_EXCLUDE_PATTERNS = [
    '.js', '.css', '.png', '.jpg', '.gif', '.svg', '.ico',
    '.woff', '.ttf', '.eot', 'google-analytics', 'baidu.com',
    'favicon', 'hot-update', 'sockjs-node', 'webpack',
]


def _is_api_candidate(url):
    """判断 URL 是否可能是后端 API 端点。"""
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()

    # 排除静态资源
    for exc in _API_EXCLUDE_PATTERNS:
        if exc in path or exc in url:
            return False

    # 匹配 API 模式
    for pat in _API_PATH_PATTERNS:
        if pat.lower() in path:
            return True

    # XHR/Fetch 通常返回 JSON，检查 Accept 头无法在此处获取，
    # 仅按路径模式判断
    return False


def _has_signature_params(url):
    """检测 API URL 中是否携带签名/鉴权参数（降级信号）。

    常见签名参数名：sign, signature, token, nonce, timestamp, appKey。
    若存在，说明 API 可能需要签名才能直调，应降级到 DOM 模式。
    """
    parsed = urlparse(url)
    query = parsed.query.lower()
    sign_keys = ('sign=', 'signature=', 'token=', 'nonce=', 'appkey=', 'appsecret=')
    return any(k in query for k in sign_keys)


class GdcicBrowser:
    """广东住建厅浏览器操作封装。

    管理 Playwright 浏览器生命周期，提供：
    1. XHR/Fetch 拦截：发现后端 API 端点
    2. API 直调模式：通过 httpx 调用发现的 API
    3. DOM 降级模式：直接从渲染后的 DOM 提取数据
    """

    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        # 拦截到的 API 端点缓存：{endpoint_key: {url, method, headers, post_data}}
        self._api_cache = {}
        # httpx 客户端（API 直调模式）
        self._httpx_client = None
        # 浏览器提取的 Cookie（供 httpx 复用）
        self._cookies_str = ''

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self):
        """启动浏览器。

        Raises:
            ImportError: Playwright 未安装
            Exception: 浏览器启动失败
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                'Playwright 未安装。请执行: pip install playwright && playwright install chromium'
            )

        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            locale='zh-CN',
            viewport={'width': 1280, 'height': 800},
        )
        self.page = self.context.new_page()

        # 注册 XHR/Fetch 请求拦截
        self.page.on('request', self._on_request)
        self.page.on('response', self._on_response)

        logger.info('[gdcic] 浏览器已启动')

    def stop(self):
        """关闭浏览器并释放资源。"""
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning('[gdcic] 浏览器关闭异常: %s', e)
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning('[gdcic] Playwright 停止异常: %s', e)
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self._playwright = None

        # 关闭 httpx 客户端
        self._close_httpx()

    # ------------------------------------------------------------------
    # XHR/Fetch 拦截
    # ------------------------------------------------------------------
    def _on_request(self, request):
        """拦截出站请求，识别 API 端点。"""
        url = request.url
        if not _is_api_candidate(url):
            return

        resource_type = request.resource_type
        if resource_type not in ('xhr', 'fetch', 'document'):
            return

        method = request.method
        logger.debug('[gdcic] 拦截到 API 请求: %s %s', method, url)

        cache_key = self._make_cache_key(url, method)
        if cache_key not in self._api_cache:
            entry = {
                'url': url,
                'method': method,
                'post_data': request.post_data,
                'has_signature': _has_signature_params(url),
            }
            self._api_cache[cache_key] = entry
            logger.info('[gdcic] 发现 API 端点: %s %s (签名=%s)',
                        method, url, entry['has_signature'])

    def _on_response(self, response):
        """拦截响应，验证 API 是否返回 JSON（进一步确认端点有效性）。"""
        url = response.url
        cache_key = self._make_cache_key(url, response.request.method)
        entry = self._api_cache.get(cache_key)
        if not entry:
            return

        content_type = response.headers.get('content-type', '')
        if 'json' in content_type or 'javascript' in content_type:
            entry['confirmed'] = True
            entry['status'] = response.status
            logger.debug('[gdcic] API 响应确认（JSON）: %s status=%d', url, response.status)
        else:
            entry['confirmed'] = False

    @staticmethod
    def _make_cache_key(url, method='GET'):
        """生成 API 缓存 key（去除 query 参数，保留路径）。"""
        parsed = urlparse(url)
        return '%s:%s' % (method, parsed.path)

    # ------------------------------------------------------------------
    # API 端点发现
    # ------------------------------------------------------------------
    def discover_api_endpoints(self):
        """访问 SPA 入口页面，等待 XHR 请求触发，收集 API 端点。

        Returns:
            dict or None: 已确认的 API 端点缓存；无可用端点时返回 None
        """
        if not self.page:
            logger.error('[gdcic] 浏览器未启动')
            return None

        for entry_url in _SPA_ENTRY_URLS:
            logger.info('[gdcic] 访问 SPA 入口: %s', entry_url)
            try:
                self.page.goto(entry_url, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)

                # 等待 SPA 加载和网络请求
                try:
                    self.page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass

                # 额外等待 JS 执行
                time.sleep(random.uniform(3, 5))

                # 尝试触发搜索，让更多 XHR 暴露
                self._try_trigger_search()

                logger.info('[gdcic] SPA 页面加载完成，已拦截 %d 个 API 候选',
                            len(self._api_cache))
            except Exception as e:
                logger.warning('[gdcic] SPA 入口加载异常: %s - %s', entry_url, e)
                continue

        # 提取 Cookie 供 httpx 复用
        self._extract_cookies()

        # 筛选已确认且无签名的端点
        valid_endpoints = {
            k: v for k, v in self._api_cache.items()
            if v.get('confirmed') and not v.get('has_signature')
        }

        if valid_endpoints:
            logger.info('[gdcic] 发现 %d 个可用 API 端点（已确认、无签名）', len(valid_endpoints))
            return valid_endpoints

        # 如果只有带签名的端点，返回 None 触发 DOM 降级
        if self._api_cache:
            logger.info('[gdcic] 发现的 API 均携带签名参数，将降级到 DOM 模式')
        return None

    def _try_trigger_search(self):
        """尝试在 SPA 页面触发搜索操作，暴露更多 API 端点。"""
        if not self.page:
            return
        try:
            # 查找搜索框
            search_input = self.page.query_selector(
                'input[type="search"], input[type="text"][placeholder*="搜索"], '
                'input[type="text"][placeholder*="关键"], input[type="text"][name*="keyword"], '
                'input[type="text"][name*="search"], input.search-input, '
                'input[placeholder*="请输入"]'
            )
            if not search_input:
                logger.debug('[gdcic] 未找到搜索框，跳过触发搜索')
                return

            # 输入一个宽泛关键词触发搜索
            search_input.fill('管道')
            time.sleep(0.5)

            # 点击搜索按钮或回车
            search_btn = self.page.query_selector(
                'button[type="submit"], button.search-btn, '
                'button.el-button--primary, .el-input-group__append button'
            )
            if search_btn:
                search_btn.click()
            else:
                search_input.press('Enter')

            # 等待结果加载
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            time.sleep(2)

            logger.info('[gdcic] 已触发搜索，暴露更多 API 端点')
        except Exception as e:
            logger.debug('[gdcic] 触发搜索失败（不影响流程）: %s', e)

    def _extract_cookies(self):
        """从浏览器上下文中提取 Cookie 字符串。"""
        if not self.context:
            return
        try:
            cookies = self.context.cookies()
            parts = ['%s=%s' % (c['name'], c['value']) for c in cookies]
            self._cookies_str = '; '.join(parts)
            logger.info('[gdcic] 提取到 %d 个 Cookie', len(cookies))
        except Exception as e:
            logger.warning('[gdcic] Cookie 提取失败: %s', e)

    # ------------------------------------------------------------------
    # API 直调模式
    # ------------------------------------------------------------------
    def fetch_list_via_api(self, keyword, page):
        """通过 httpx 直调发现的 API 端点获取列表数据。

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list or None: API 返回的原始数据列表；失败返回 None
        """
        import httpx

        client = self._get_httpx_client()
        if not client:
            return None

        # 选择一个列表类 API 端点（优先选 confirmed 的）
        list_endpoint = self._pick_list_endpoint()
        if not list_endpoint:
            logger.warning('[gdcic] 无可用列表 API 端点')
            return None

        url = list_endpoint['url']
        method = list_endpoint['method']

        # 构造请求参数（猜测常见参数名）
        params = self._build_api_params(keyword, page)

        try:
            time.sleep(random.uniform(1, 2))
            logger.info('[gdcic] API 直调: %s %s params=%s', method, url, params)

            if method == 'POST':
                response = client.post(url, json=params, timeout=30.0)
            else:
                response = client.get(url, params=params, timeout=30.0)

            if response.status_code != 200:
                logger.warning('[gdcic] API 返回 HTTP %d: %s', response.status_code, url)
                return None

            data = response.json()

            # 尝试多种常见响应结构
            rows = (data.get('data') or data.get('rows') or data.get('list')
                    or data.get('result') or data.get('records') or [])
            if isinstance(rows, dict):
                rows = rows.get('rows') or rows.get('list') or rows.get('records') or []

            if not isinstance(rows, list):
                logger.warning('[gdcic] API 返回非列表数据: type=%s', type(rows).__name__)
                return None

            logger.info('[gdcic] API 返回 %d 条数据', len(rows))
            return rows

        except Exception as e:
            logger.warning('[gdcic] API 直调失败: %s - %s', url, e)
            return None

    def _pick_list_endpoint(self):
        """从缓存中选择一个列表类 API 端点。"""
        for key, entry in self._api_cache.items():
            if entry.get('confirmed') and not entry.get('has_signature'):
                url_lower = entry['url'].lower()
                # 优先匹配列表/查询类端点
                for kw in ('list', 'query', 'search', 'getdata', 'getlist', 'page'):
                    if kw in url_lower:
                        return entry
        # 退而求其次：任意已确认端点
        for entry in self._api_cache.values():
            if entry.get('confirmed') and not entry.get('has_signature'):
                return entry
        return None

    def _get_httpx_client(self):
        """获取或创建 httpx 客户端。"""
        import httpx

        if self._httpx_client is not None:
            return self._httpx_client

        try:
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'Referer': 'https://skypt.gdcic.net/',
            }
            if self._cookies_str:
                headers['Cookie'] = self._cookies_str

            self._httpx_client = httpx.Client(
                timeout=httpx.Timeout(30.0, connect=15.0),
                follow_redirects=True,
                headers=headers,
            )
            return self._httpx_client
        except Exception as e:
            logger.error('[gdcic] httpx 客户端创建失败: %s', e)
            return None

    def _close_httpx(self):
        """关闭 httpx 客户端。"""
        if self._httpx_client is not None:
            try:
                self._httpx_client.close()
            except Exception:
                pass
            self._httpx_client = None

    @staticmethod
    def _build_api_params(keyword, page):
        """构造 API 请求参数（猜测常见参数名）。"""
        return {
            'keyword': keyword,
            'searchKey': keyword,
            'name': keyword,
            'pageNo': page,
            'pageNum': page,
            'page': page,
            'pageSize': 20,
        }

    # ------------------------------------------------------------------
    # DOM 降级模式
    # ------------------------------------------------------------------
    def fetch_list_via_dom(self, keyword, page):
        """通过 Playwright 渲染页面并返回 DOM HTML。

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            str or None: 渲染后的页面 HTML；失败返回 None
        """
        if not self.page:
            logger.error('[gdcic] 浏览器未启动')
            return None

        # 尝试在页面中输入关键词搜索
        try:
            html = self._search_and_render(keyword, page)
            if html:
                return html
        except Exception as e:
            logger.warning('[gdcic] DOM 搜索渲染失败: %s', e)

        # 降级：尝试直接访问带参数的 URL
        for base_url in _SPA_ENTRY_URLS:
            url = '%s?keyword=%s&page=%d' % (base_url, keyword, page)
            html = self._load_page(url)
            if html and self._has_list_content(html):
                return html

        logger.warning('[gdcic] DOM 模式未获取到有效内容: keyword=%s page=%d', keyword, page)
        return None

    def _search_and_render(self, keyword, page):
        """在 SPA 页面中执行搜索并返回渲染后的 HTML。"""
        # 确保在 SPA 页面上
        current_url = self.page.url or ''
        if 'skypt.gdcic.net' not in current_url:
            for entry_url in _SPA_ENTRY_URLS:
                try:
                    self.page.goto(entry_url, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)
                    try:
                        self.page.wait_for_load_state('networkidle', timeout=10000)
                    except Exception:
                        pass
                    time.sleep(2)
                    break
                except Exception:
                    continue

        # 查找搜索框并输入关键词
        search_input = self.page.query_selector(
            'input[type="search"], input[type="text"][placeholder*="搜索"], '
            'input[type="text"][placeholder*="关键"], input[type="text"][name*="keyword"], '
            'input.search-input, input[placeholder*="请输入"]'
        )
        if not search_input:
            logger.debug('[gdcic] DOM 模式：未找到搜索框')
            return None

        search_input.fill(keyword)
        time.sleep(0.5)

        search_btn = self.page.query_selector(
            'button[type="submit"], button.search-btn, '
            'button.el-button--primary, .el-input-group__append button'
        )
        if search_btn:
            search_btn.click()
        else:
            search_input.press('Enter')

        # 等待结果加载
        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        time.sleep(random.uniform(2, 3))

        # 翻页
        if page > 1:
            self._goto_page(page)

        return self.page.content()

    def _goto_page(self, page_num):
        """点击分页组件跳转到指定页。"""
        try:
            # Element UI 分页组件
            pager_btn = self.page.query_selector(
                'li.number:has-text("%d"), '
                'button.btn-pagination:has-text("%d"), '
                'a.pagination-link:has-text("%d")' % (page_num, page_num, page_num)
            )
            if pager_btn:
                pager_btn.click()
                time.sleep(random.uniform(1, 2))
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
                return True

            # 下一页按钮
            next_btn = self.page.query_selector(
                'button.btn-next, .el-pagination .btn-next, '
                'a.next, li.next a'
            )
            if next_btn and not next_btn.is_disabled():
                for _ in range(page_num - 1):
                    next_btn.click()
                    time.sleep(random.uniform(0.5, 1))
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.debug('[gdcic] 分页跳转失败: %s', e)
        return False

    def _load_page(self, url):
        """加载指定 URL 并返回 HTML。"""
        try:
            time.sleep(random.uniform(2, 4))
            logger.info('[gdcic] 加载页面: %s', url)
            self.page.goto(url, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)

            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass

            time.sleep(random.uniform(1, 2))
            return self.page.content()
        except Exception as e:
            logger.warning('[gdcic] 页面加载失败: %s - %s', url, e)
            return None

    @staticmethod
    def _has_list_content(html):
        """检查 HTML 是否包含列表内容（非空页面）。"""
        if not html:
            return False

        import re
        # 检查是否有表格行或列表项
        li_count = len(re.findall(r'<li[^>]*>', html, re.I))
        tr_count = len(re.findall(r'<tr[^>]*>', html, re.I))
        if li_count >= 3 or tr_count >= 3:
            return True

        # 检查是否有日期模式
        date_count = len(re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', html))
        if date_count >= 2:
            return True

        return False
