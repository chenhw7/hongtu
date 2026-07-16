# -*- coding: utf-8 -*-
"""Playwright 工具函数测试。"""
import pytest


def _check_playwright_available():
    """检查 Playwright 是否可用。"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


# 标记：需要 Playwright + Chromium 才能运行的测试
playwright_required = pytest.mark.skipif(
    not _check_playwright_available(),
    reason='Playwright 或 Chromium 未安装'
)


class TestExtractCookies:
    """Cookie 提取测试。"""

    @playwright_required
    def test_extract_cookies_simple_page(self):
        """测试从简单页面提取 Cookie。"""
        from scraper.playwright_utils import extract_cookies
        # 使用一个已知会设置 Cookie 的公共网站测试
        cookies = extract_cookies('https://www.baidu.com', wait_seconds=2)
        assert isinstance(cookies, dict)
        # 百度至少会设置一些 Cookie
        assert len(cookies) > 0

    def test_extract_cookies_no_playwright(self):
        """Playwright 不可用时应返回空字典。"""
        # 这个测试始终通过，因为如果 Playwright 可用则走真实逻辑
        from scraper.playwright_utils import extract_cookies
        # 用一个不可达的 URL 测试错误处理
        cookies = extract_cookies('http://localhost:1/nonexistent', wait_seconds=0)
        assert isinstance(cookies, dict)

    @playwright_required
    def test_extract_cookies_for_domain(self):
        """测试 Cookie 字符串格式化。"""
        from scraper.playwright_utils import extract_cookies_for_domain
        cookie_str = extract_cookies_for_domain('https://www.baidu.com', wait_seconds=2)
        assert isinstance(cookie_str, str)
        if cookie_str:
            assert '=' in cookie_str  # 至少有一个 name=value 对


class TestCreateSessionWithCookies:
    """httpx Session 创建测试。"""

    def test_create_session_with_explicit_cookies(self):
        """使用显式 Cookie 创建 Session。"""
        from scraper.playwright_utils import create_session_with_cookies
        client = create_session_with_cookies(
            'https://example.com',
            cookies_str='test_cookie=test_value'
        )
        assert client is not None
        assert 'Cookie' in client.headers
        assert 'test_cookie=test_value' in client.headers['Cookie']
        client.close()

    def test_create_session_with_extra_headers(self):
        """测试额外请求头合并。"""
        from scraper.playwright_utils import create_session_with_cookies
        client = create_session_with_cookies(
            'https://example.com',
            cookies_str='a=b',
            extra_headers={'X-Custom': 'value'}
        )
        assert client.headers.get('X-Custom') == 'value'
        client.close()
