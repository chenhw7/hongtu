# -*- coding: utf-8 -*-
"""广东省住建厅（广东建设信息网 www.gdcic.net）采集模块。

技术方案：
1. 优先策略：用 Playwright 访问 SPA 页面，拦截网络请求发现后端 API 端点，然后降级为 httpx 直连 API
2. 降级策略：如果 API 有签名参数无法直接调用，则保持 Playwright 全流程渲染，从 DOM 提取数据

模块结构：
- browser.py: Playwright SPA 渲染 + XHR 拦截
- parser.py:  API JSON 解析或 DOM 解析 → Lead dict
- utils.py:   gdcic 专用工具函数
"""
import logging
import time

from scraper.base import BaseScraper, ScraperStopped
from scraper.keywords import PLATFORM_KEYWORDS_FINAL
from scraper.gdcic.browser import GdcicBrowser
from scraper.gdcic.parser import parse_api_list, parse_dom_list

logger = logging.getLogger(__name__)


class GdcicScraper(BaseScraper):
    """广东住建厅采集器。

    继承 BaseScraper 以复用 save_leads()、进度追踪、暂停/停止等功能。
    覆盖 run() 方法以管理 Playwright 浏览器生命周期。
    优先使用 httpx + API 模式，降级到 Playwright DOM 模式。
    """

    source_type = 'gdcic'
    base_url = 'https://www.gdcic.net'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(PLATFORM_KEYWORDS_FINAL)
        self.delay_min = 2
        self.delay_max = 4
        self.browser = None
        self.api_mode = False  # True=API 直调模式，False=DOM 渲染模式

    def run(self, keywords=None, max_pages=5):
        """执行采集，管理 Playwright 浏览器生命周期。

        Args:
            keywords: 关键词列表，None 时使用 PLATFORM_KEYWORDS_FINAL
            max_pages: 每个关键词最大页数

        Returns:
            int: 新增线索数量
        """
        if keywords is None:
            keywords = self.keywords

        logger.info('[gdcic] 开始采集，关键词: %s，每词最多 %d 页', keywords, max_pages)

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
            # 2. 启动 Playwright 浏览器
            headless = True
            if self.app:
                headless = self.app.config.get('GDCIC_HEADLESS', True)
            self.browser = GdcicBrowser(headless=headless)
            self.browser.start()

            # 3. 尝试发现 API 端点
            api_endpoints = self.browser.discover_api_endpoints()
            if api_endpoints:
                logger.info('[gdcic] 发现 API 端点，切换到 API 直调模式: %s', api_endpoints)
                self.api_mode = True
            else:
                logger.warning('[gdcic] 未发现可用 API，降级到 DOM 渲染模式')
                self.api_mode = False

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
                    logger.info('[gdcic] 关键词="%s" 第 %d 页', keyword, page)
                    self._progress_update(
                        current_page=page,
                        message='采集关键词「%s」第 %d/%d 页' % (keyword, page, max_pages),
                    )

                    leads_data = self._scrape_page(keyword, page)

                    if leads_data is None:
                        failed_units.append('%s 第%d页' % (keyword, page))
                        logger.warning('[gdcic] 第%d页采集失败，跳过关键词「%s」', page, keyword)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        time.sleep(self.delay_max * 2)
                        break

                    if len(leads_data) == 0:
                        logger.info('[gdcic] 关键词="%s" 第%d页无结果，下一关键词', keyword, page)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        break

                    # 5. 保存线索
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    done_pages += 1
                    logger.info('[gdcic] 关键词="%s" 第%d页: 获取%d条，新增%d条',
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
                logger.info('[gdcic] 采集完成，共新增 %d 条线索', total_new)

            return total_new

        except ScraperStopped:
            logger.info('[gdcic] 采集已被手动停止，累计新增 %d 条线索', total_new)
            self.update_task(task_id, '已停止', result_count=total_new)
            self._progress_finish('已停止', collected=total_new)
            return total_new

        except Exception as e:
            logger.exception('[gdcic] 采集异常: %s', e)
            self.update_task(task_id, '失败', result_count=total_new, error_msg=str(e))
            self._progress_finish('失败', collected=total_new, error_msg=str(e))
            return total_new

        finally:
            # 关闭浏览器
            if self.browser:
                self.browser.stop()
                self.browser = None
            self._progress_clear_control()

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果。

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict]: 线索列表，None 表示请求失败
        """
        if not self.browser:
            logger.error('[gdcic] 浏览器未启动')
            return None

        if self.api_mode:
            # API 直调模式
            leads = self.browser.fetch_list_via_api(keyword, page)
            if leads is None:
                return None
            return parse_api_list(leads, self.base_url)
        else:
            # DOM 渲染模式
            html = self.browser.fetch_list_via_dom(keyword, page)
            if not html:
                return None
            return parse_dom_list(html, self.base_url)
