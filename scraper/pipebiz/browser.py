# -*- coding: utf-8 -*-
"""pipebiz Playwright 浏览器操作封装。

中国管道商务网（chinapipe.net）全站有 JS 重定向保护，
HTTP 直连返回 JS Challenge 页面。本模块使用 Playwright 渲染页面并提取 DOM 内容。
"""
import logging
import random
import time

logger = logging.getLogger(__name__)

# 常见搜索 URL 模板（按优先级尝试）
_SEARCH_URL_TEMPLATES = [
    'https://www.chinapipe.net/search/?kw={keyword}&page={page}',
    'https://www.chinapipe.net/search.html?kw={keyword}&page={page}',
    'https://www.chinapipe.net/zhaobiao/?kw={keyword}&page={page}',
    'https://www.chinapipe.net/news/search.html?kw={keyword}&page={page}',
]

# 已知栏目 URL（搜索结果不可用时的降级路径）
_CATEGORY_URLS = [
    'https://www.chinapipe.net/zhaobiao/',       # 招标信息
    'https://www.chinapipe.net/project/',         # 工程项目
    'https://www.chinapipe.net/news/',            # 行业资讯
]

# Playwright 页面加载超时（毫秒）
_PAGE_TIMEOUT = 30000


class PipebizBrowser:
    """管道商务网浏览器操作封装。

    管理 Playwright 浏览器生命周期，提供页面加载和内容提取方法。
    整个采集周期共享一个浏览器实例，避免反复启动。
    """

    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """启动浏览器并访问首页，等待 JS Challenge 完成。

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

        # 访问首页，等待 JS Challenge 完成
        logger.info('[pipebiz] 启动浏览器，访问首页...')
        try:
            self.page.goto('https://www.chinapipe.net/', wait_until='networkidle', timeout=_PAGE_TIMEOUT)
            # 额外等待 JS 执行
            time.sleep(random.uniform(3, 5))
            logger.info('[pipebiz] 首页加载完成，JS Challenge 已通过')
        except Exception as e:
            logger.warning('[pipebiz] 首页加载异常（继续尝试）: %s', e)

    def stop(self):
        """关闭浏览器并释放资源。"""
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning('[pipebiz] 浏览器关闭异常: %s', e)
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning('[pipebiz] Playwright 停止异常: %s', e)
        finally:
            self.browser = None
            self.context = None
            self.page = None
            self._playwright = None

    def search_keyword(self, keyword, page_num=1):
        """搜索关键词并返回结果列表的 HTML。

        尝试以下路径（按优先级）：
        1. 搜索页面（如果有搜索框）
        2. 工程信息/招标信息列表页
        3. 直接访问已知栏目 URL

        Args:
            keyword: 搜索关键词
            page_num: 页码（从 1 开始）

        Returns:
            str: 结果列表页 HTML，失败返回 None
        """
        if not self.page:
            logger.error('[pipebiz] 浏览器未启动')
            return None

        # 策略 1：尝试搜索 URL 模板
        for url_tpl in _SEARCH_URL_TEMPLATES:
            url = url_tpl.format(keyword=keyword, page=page_num)
            html = self._load_page(url)
            if html and self._has_search_results(html):
                logger.info('[pipebiz] 搜索成功: %s (模板: %s)', keyword, url_tpl)
                return html

        # 策略 2：尝试在页面搜索框中输入关键词
        html = self._try_search_form(keyword)
        if html and self._has_search_results(html):
            return html

        # 策略 3：降级到栏目 URL（仅第 1 页）
        if page_num == 1:
            for url in _CATEGORY_URLS:
                html = self._load_page(url)
                if html and self._has_search_results(html):
                    logger.info('[pipebiz] 栏目降级成功: %s', url)
                    return html

        logger.warning('[pipebiz] 搜索无结果: keyword=%s, page=%d', keyword, page_num)
        return None

    def get_detail(self, detail_url):
        """获取详情页 HTML。

        Args:
            detail_url: 详情页完整 URL

        Returns:
            str: 详情页 HTML，失败返回 None
        """
        if not self.page:
            logger.error('[pipebiz] 浏览器未启动')
            return None

        return self._load_page(detail_url)

    def _load_page(self, url):
        """加载指定 URL 并返回 HTML。

        Args:
            url: 页面 URL

        Returns:
            str: 页面 HTML，失败返回 None
        """
        try:
            # 限速：每次页面操作前随机延迟 2-4 秒
            delay = random.uniform(2, 4)
            time.sleep(delay)

            logger.info('[pipebiz] 加载页面: %s', url)
            self.page.goto(url, wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)

            # 等待内容加载（JS 渲染）
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass  # networkidle 超时不算严重错误

            # 额外等待动态内容
            time.sleep(random.uniform(1, 2))

            html = self.page.content()
            return html
        except Exception as e:
            logger.warning('[pipebiz] 页面加载失败: %s - %s', url, e)
            return None

    def _try_search_form(self, keyword):
        """尝试在页面搜索框中输入关键词并提交。

        Returns:
            str: 搜索结果页 HTML，失败返回 None
        """
        try:
            # 先回到首页
            self.page.goto('https://www.chinapipe.net/', wait_until='domcontentloaded', timeout=_PAGE_TIMEOUT)
            time.sleep(2)

            # 查找搜索框
            search_input = self.page.query_selector(
                'input[type="search"], input[type="text"][name*="key"], '
                'input[type="text"][name*="search"], input[type="text"][name*="q"], '
                'input.search-input, input#search-input, input[placeholder*="搜索"]'
            )
            if not search_input:
                logger.debug('[pipebiz] 未找到搜索框')
                return None

            # 输入关键词
            search_input.fill(keyword)
            time.sleep(0.5)

            # 查找并点击搜索按钮
            search_btn = self.page.query_selector(
                'button[type="submit"], input[type="submit"], '
                'button.search-btn, button.btn-search, .search-submit'
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

            return self.page.content()
        except Exception as e:
            logger.warning('[pipebiz] 搜索表单操作失败: %s', e)
            return None

    @staticmethod
    def _has_search_results(html):
        """检查 HTML 是否包含搜索结果（非空页面/错误页面）。

        简单的启发式检查：页面中是否有列表项或含日期的链接。
        """
        if not html:
            return False

        # 检查是否有常见的列表元素
        import re
        # 检查 <li> 或 <a> 标签数量（列表页通常有多条）
        li_count = len(re.findall(r'<li[^>]*>', html, re.I))
        if li_count >= 3:
            return True

        # 检查是否有日期模式（YYYY-MM-DD）
        date_count = len(re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', html))
        if date_count >= 2:
            return True

        return False
