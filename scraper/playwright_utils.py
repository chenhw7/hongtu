# -*- coding: utf-8 -*-
"""Playwright 浏览器辅助工具。

为需要 JS 渲染或 CDN Cookie 的数据源提供通用的 Cookie 提取功能。
典型用法：先用 Playwright 无头浏览器加载目标站点首页，等待 JS Challenge
自动解题后提取 Cookie，再用 httpx 带 Cookie 调用 JSON API。
"""
import logging
import time

logger = logging.getLogger(__name__)


def extract_cookies(url, wait_seconds=5, headless=True):
    """用 Playwright 加载页面并提取 Cookie。

    Args:
        url: 目标页面 URL（通常是目标站点首页）
        wait_seconds: 页面加载后等待 JS 执行的时间（秒）
        headless: 是否使用无头模式（默认 True）

    Returns:
        dict: Cookie 字典 {name: value}，失败返回空字典
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error('Playwright 未安装。请执行: pip install playwright && playwright install chromium')
        return {}

    cookies = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
            )
            page = context.new_page()

            logger.info('[playwright] 加载页面: %s', url)
            page.goto(url, wait_until='networkidle', timeout=30000)

            # 等待 JS 执行（CDN Challenge 通常需要几秒）
            if wait_seconds > 0:
                logger.info('[playwright] 等待 %d 秒让 JS 执行...', wait_seconds)
                time.sleep(wait_seconds)

            # 提取所有 Cookie
            for cookie in context.cookies():
                cookies[cookie['name']] = cookie['value']

            logger.info('[playwright] 提取到 %d 个 Cookie: %s',
                        len(cookies), list(cookies.keys()))

            browser.close()

    except Exception as e:
        logger.error('[playwright] Cookie 提取失败: %s', e)

    return cookies


def extract_cookies_for_domain(domain_url, api_url=None, wait_seconds=5):
    """为指定域名提取 Cookie，并格式化为 httpx 可用的 Cookie 字符串。

    Args:
        domain_url: 域名首页 URL（如 https://tzxm.gd.gov.cn）
        api_url: 可选的 API URL，用于验证 Cookie 是否有效
        wait_seconds: JS 等待时间

    Returns:
        str: Cookie 字符串（"name1=value1; name2=value2"），可直接用于 httpx headers
    """
    cookies = extract_cookies(domain_url, wait_seconds=wait_seconds)
    if not cookies:
        return ''
    return '; '.join(f'{k}={v}' for k, v in cookies.items())


def create_session_with_cookies(base_url, cookies_str=None, extra_headers=None):
    """创建带 Cookie 的 httpx Client。

    如果未提供 cookies_str，会自动用 Playwright 从 base_url 提取。

    Args:
        base_url: 目标站点基础 URL
        cookies_str: 已有的 Cookie 字符串（可选）
        extra_headers: 额外的请求头

    Returns:
        httpx.Client: 带 Cookie 的 HTTP 客户端
    """
    import httpx

    if cookies_str is None:
        cookies_str = extract_cookies_for_domain(base_url)

    headers = {
        'Accept': 'application/json, text/html, */*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if cookies_str:
        headers['Cookie'] = cookies_str
    if extra_headers:
        headers.update(extra_headers)

    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
        headers=headers,
    )
