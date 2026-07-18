# -*- coding: utf-8 -*-
"""北极星环保网（bjx.com.cn）采集模块。

使用 Playwright WAF Cookie 提取 + httpx 请求策略：
- 环保频道（huanbao.bjx.com.cn）和招投标栏目（news.bjx.com.cn/zb/）
  被 WAF 拦截，返回 JS Challenge 页面
- Playwright 渲染页面通过 WAF 检查后提取 Cookie
- httpx 携带 Cookie 请求列表页和详情页（SSR，无需 JS 渲染）
- Cookie 刷新机制（间隔 300 秒）

模块结构：
- browser.py: Playwright 浏览器管理 + Cookie 提取
- parser.py:  HTML DOM 解析 → Lead dict
- utils.py:   Cookie 管理、请求头构建、文本清理
"""
import logging
import time

import httpx
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ScraperStopped
from scraper.keywords import BJX_KEYWORDS_FINAL
from scraper.bjx.browser import BjxBrowser
from scraper.bjx.parser import parse_list_page, parse_detail_page
from scraper.bjx.utils import (
    build_bjx_headers,
    is_waf_challenge_page,
    should_refresh_cookies,
)

logger = logging.getLogger(__name__)


class BjxScraper(BaseScraper):
    """北极星环保网采集器。

    继承 BaseScraper 以复用 save_leads()、进度追踪、暂停/停止等功能。
    覆写 run() 方法以管理 Playwright 浏览器生命周期。
    采用 Playwright Cookie + httpx 混合模式：先获取 WAF Cookie，再用 httpx
    携带 Cookie 请求列表页和详情页。
    """

    source_type = 'bjx'
    base_url = 'https://huanbao.bjx.com.cn'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(BJX_KEYWORDS_FINAL)
        # 限速配置（秒）
        self.delay_min = 2
        self.delay_max = 4
        # Playwright 浏览器实例
        self.browser = None
        # Cookie 状态
        self._cookies_str = ''
        self._last_cookie_time = 0
        # httpx 客户端
        self._http_client = None

    def run(self, keywords=None, max_pages=5):
        """执行采集，管理 Playwright 浏览器生命周期。

        流程：
        1. 启动 Playwright 浏览器 → 获取 WAF Cookie
        2. 使用 httpx + Cookie 请求列表页和详情页
        3. Cookie 过期时自动刷新
        4. 采集完成后关闭浏览器

        Args:
            keywords: 关键词列表，None 时使用 BJX_KEYWORDS_FINAL
            max_pages: 每个关键词最大页数

        Returns:
            int: 新增线索数量
        """
        if keywords is None:
            keywords = self.keywords

        logger.info('[bjx] 开始采集，关键词: %s，每词最多 %d 页', keywords, max_pages)

        # 1. 创建任务记录
        task = self.create_task(self.source_type, self.base_url)
        task_id = task.id

        # 初始化实时进度
        self._progress_start(task_id, len(keywords), max_pages)

        total_new = 0
        done_pages = 0
        failed_units = []
        self._seen_keys = set()

        try:
            # 2. 启动 Playwright 浏览器并获取 Cookie
            headless = True
            if self.app:
                headless = self.app.config.get('BJX_HEADLESS', True)
            self.browser = BjxBrowser(headless=headless)
            self.browser.start()
            self._cookies_str = self.browser.extract_cookies()
            self._last_cookie_time = time.time()

            if not self._cookies_str:
                logger.warning('[bjx] 未获取到 WAF Cookie，后续请求可能被拦截')

            # 3. 创建 httpx 客户端
            self._create_http_client()

            # 4. 遍历关键词和页数
            for kw_index, keyword in enumerate(keywords, start=1):
                self._check_pause_and_stop()
                self._progress_update(
                    keyword_index=kw_index,
                    current_keyword=keyword,
                    message='采集关键词「%s」(%d/%d)' % (keyword, kw_index, len(keywords)),
                )

                for page in range(1, max_pages + 1):
                    self._check_pause_and_stop()
                    logger.info('[bjx] 关键词="%s" 第 %d 页', keyword, page)
                    self._progress_update(
                        current_page=page,
                        message='采集关键词「%s」第 %d/%d 页' % (keyword, page, max_pages),
                    )

                    leads_data = self._scrape_page(keyword, page)

                    if leads_data is None:
                        failed_units.append('%s 第%d页' % (keyword, page))
                        logger.warning('[bjx] 第%d页采集失败，跳过关键词「%s」', page, keyword)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        time.sleep(self.delay_max * 2)
                        break

                    if len(leads_data) == 0:
                        logger.info('[bjx] 关键词="%s" 第%d页无结果，下一关键词', keyword, page)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        break

                    # 5. 保存线索
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    done_pages += 1
                    logger.info('[bjx] 关键词="%s" 第%d页: 获取%d条，新增%d条',
                                keyword, page, len(leads_data), new_count)
                    self._progress_update(
                        done_pages=done_pages,
                        collected=total_new,
                        message='关键词「%s」第 %d 页: 新增 %d 条（累计 %d 条）'
                                % (keyword, page, new_count, total_new),
                    )

            # 6. 更新任务状态
            if failed_units:
                error_msg = '以下采集单元失败: ' + '；'.join(failed_units)
                self.update_task(task_id, '失败', result_count=total_new, error_msg=error_msg)
                self._progress_finish('失败', collected=total_new, error_msg=error_msg)
            else:
                self.update_task(task_id, '完成', result_count=total_new)
                self._progress_finish('完成', collected=total_new)
                logger.info('[bjx] 采集完成，共新增 %d 条线索', total_new)

            return total_new

        except ScraperStopped:
            logger.info('[bjx] 采集已被手动停止，累计新增 %d 条线索', total_new)
            self.update_task(task_id, '已停止', result_count=total_new)
            self._progress_finish('已停止', collected=total_new)
            return total_new

        except Exception as e:
            logger.exception('[bjx] 采集异常: %s', e)
            self.update_task(task_id, '失败', result_count=total_new, error_msg=str(e))
            self._progress_finish('失败', collected=total_new, error_msg=str(e))
            return total_new

        finally:
            # 关闭 httpx 客户端
            self._close_http_client()
            # 关闭浏览器
            if self.browser:
                self.browser.stop()
                self.browser = None
            self._progress_clear_control()

    def _create_http_client(self):
        """创建带 WAF Cookie 的 httpx 客户端。"""
        self._close_http_client()
        headers = build_bjx_headers(
            cookies_str=self._cookies_str,
            referer=self.base_url,
        )
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            headers=headers,
        )

    def _close_http_client(self):
        """关闭 httpx 客户端。"""
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None

    def _refresh_cookies_if_needed(self):
        """检查并刷新 Cookie（过期或被 WAF 拦截时）。"""
        if not should_refresh_cookies(self._last_cookie_time, self._cookies_str):
            return

        if not self.browser:
            logger.warning('[bjx] 浏览器未启动，无法刷新 Cookie')
            return

        logger.info('[bjx] 刷新 WAF Cookie...')
        new_cookies = self.browser.refresh_cookies()
        if new_cookies:
            self._cookies_str = new_cookies
            self._last_cookie_time = time.time()
            # 重建 httpx 客户端以携带新 Cookie
            self._create_http_client()
            logger.info('[bjx] WAF Cookie 已刷新')
        else:
            logger.warning('[bjx] Cookie 刷新失败，继续使用旧 Cookie')

    def _http_get(self, url, max_retries=3):
        """使用 httpx 发起 GET 请求，带限速、重试和 Cookie 刷新。

        当检测到 WAF 拦截（返回 JS Challenge 页面或 403）时，自动刷新 Cookie 重试。

        Args:
            url: 请求 URL
            max_retries: 最大重试次数

        Returns:
            str: 响应 HTML，失败返回 None
        """
        import random

        for attempt in range(1, max_retries + 1):
            try:
                # 限速
                time.sleep(random.uniform(self.delay_min, self.delay_max))

                logger.info('[bjx] HTTP GET (attempt %d): %s', attempt, url)
                response = self._http_client.get(url)

                if response.status_code == 200:
                    html = response.text
                    # 检测 WAF 拦截
                    if is_waf_challenge_page(html):
                        logger.warning('[bjx] 被 WAF 拦截（JS Challenge），尝试刷新 Cookie')
                        if attempt < max_retries:
                            self._refresh_cookies_if_needed()
                            time.sleep(random.uniform(3, 5))
                            continue
                        return None
                    return html

                elif response.status_code in (403, 401, 419, 429):
                    logger.warning('[bjx] HTTP %d，尝试刷新 Cookie 后重试', response.status_code)
                    if attempt < max_retries:
                        self._refresh_cookies_if_needed()
                        time.sleep(random.uniform(3, 5))
                        continue
                    return None

                else:
                    logger.warning('[bjx] HTTP %d: %s', response.status_code, url)
                    if attempt < max_retries:
                        time.sleep(random.uniform(2, 4))
                        continue
                    return None

            except httpx.TimeoutException:
                logger.warning('[bjx] 请求超时 (attempt %d): %s', attempt, url)
            except httpx.ConnectError:
                logger.warning('[bjx] 连接失败 (attempt %d): %s', attempt, url)
            except Exception as e:
                logger.warning('[bjx] 请求异常 (attempt %d): %s - %s', attempt, url, e)

            if attempt < max_retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

        logger.error('[bjx] 请求最终失败: %s', url)
        return None

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果。

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict]: 线索列表，None 表示请求失败
        """
        # 检查 Cookie 是否需要刷新
        self._refresh_cookies_if_needed()

        # 1. 获取列表页 HTML（httpx + Cookie）
        # 优先尝试招投标栏目搜索
        list_url = f'https://news.bjx.com.cn/zb/list.html?kw={keyword}&page={page}'
        html = self._http_get(list_url)

        # 如果招投标栏目无结果，尝试环保频道
        if not html or not self._has_results(html):
            list_url = f'https://huanbao.bjx.com.cn/news/list.html?kw={keyword}&page={page}'
            html = self._http_get(list_url)

        if not html:
            # httpx 失败时降级到 Playwright 全程渲染
            logger.info('[bjx] httpx 请求失败，降级到 Playwright 渲染')
            if self.browser:
                html = self.browser.search_keyword(keyword, page_num=page)

        if not html:
            return None

        # 2. 解析列表页
        leads = parse_list_page(html, self.base_url)
        if not leads:
            return []

        # 3. 请求详情页（对每条线索）
        for lead in leads:
            detail_url = lead.get('source_url')
            if not detail_url:
                continue

            # 去重检查：进程内缓存
            dedup_key = self._lead_dedup_key(lead)
            if dedup_key and dedup_key in self._seen_keys:
                continue

            try:
                self._check_pause_and_stop()

                detail_html = self._http_get(detail_url)
                if not detail_html and self.browser:
                    # 降级到 Playwright
                    detail_html = self.browser.load_page(detail_url)

                if detail_html:
                    detail_data = parse_detail_page(detail_html, self.base_url)
                    # 合并详情字段到列表页 lead
                    for key, value in detail_data.items():
                        if key == 'attachments':
                            lead['attachments'] = value
                        elif key not in lead or not lead[key]:
                            lead[key] = value
                    # 保存原始 HTML 快照
                    lead['_raw_html'] = detail_html
            except ScraperStopped:
                raise
            except Exception as e:
                logger.warning('[bjx] 详情页解析失败: %s - %s', detail_url, e)

            if dedup_key:
                self._seen_keys.add(dedup_key)

        return leads

    @staticmethod
    def _has_results(html):
        """检查 HTML 是否包含搜索结果。"""
        if not html:
            return False

        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception:
            soup = BeautifulSoup(html, 'html.parser')

        # 检查是否有列表元素
        items = soup.select(
            'ul.list li, ul.news-list li, div.list-item, '
            'div.news-item, div.article-list li, table tbody tr'
        )
        if len(items) >= 1:
            return True

        # 检查是否有日期模式
        import re
        date_count = len(re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', html))
        if date_count >= 2:
            return True

        return False
