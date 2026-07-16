# -*- coding: utf-8 -*-
"""中国管道商务网（chinapipe.net）采集模块。

使用 Playwright 渲染页面 + DOM 解析策略：
- 全站有 JS 重定向保护，HTTP 直连返回 JS Challenge 页面
- Playwright 可以处理任何 JS Challenge 或动态加载
- DOM 解析比 API 调用更鲁棒，可适配页面结构变化

模块结构：
- browser.py: Playwright 页面加载和内容提取
- parser.py:  HTML DOM 解析 → Lead dict
- utils.py:   pipebiz 专用工具函数
"""
import logging
import time

from scraper.base import BaseScraper, ScraperStopped
from scraper.keywords import CCGP_KEYWORDS_FINAL
from scraper.pipebiz.browser import PipebizBrowser
from scraper.pipebiz.parser import parse_search_results, parse_detail_page

logger = logging.getLogger(__name__)


class PipebizScraper(BaseScraper):
    """中国管道商务网采集器。

    继承 BaseScraper 以复用 save_leads()、进度追踪、暂停/停止等功能。
    覆盖 run() 方法以管理 Playwright 浏览器生命周期。
    不使用 httpx，全程使用 Playwright 浏览器。
    """

    source_type = 'pipebiz'
    base_url = 'https://www.chinapipe.net'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(CCGP_KEYWORDS_FINAL)
        # Playwright 限速配置（秒）
        self.delay_min = 2
        self.delay_max = 4
        self.browser = None

    def run(self, keywords=None, max_pages=5):
        """执行采集，管理 Playwright 浏览器生命周期。

        Args:
            keywords: 关键词列表，None 时使用 CCGP_KEYWORDS_FINAL
            max_pages: 每个关键词最大页数

        Returns:
            int: 新增线索数量
        """
        if keywords is None:
            keywords = self.keywords

        logger.info('[pipebiz] 开始采集，关键词: %s，每词最多 %d 页', keywords, max_pages)

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
                headless = self.app.config.get('PIPEBIZ_HEADLESS', True)
            self.browser = PipebizBrowser(headless=headless)
            self.browser.start()

            # 3. 遍历关键词和页数
            for kw_index, keyword in enumerate(keywords, start=1):
                self._check_pause_and_stop()
                self._progress_update(
                    keyword_index=kw_index,
                    current_keyword=keyword,
                    message='采集关键词「%s」(%d/%d)' % (keyword, kw_index, len(keywords)),
                )

                for page in range(1, max_pages + 1):
                    self._check_pause_and_stop()
                    logger.info('[pipebiz] 关键词="%s" 第 %d 页', keyword, page)
                    self._progress_update(
                        current_page=page,
                        message='采集关键词「%s」第 %d/%d 页' % (keyword, page, max_pages),
                    )

                    leads_data = self._scrape_page(keyword, page)

                    if leads_data is None:
                        failed_units.append('%s 第%d页' % (keyword, page))
                        logger.warning('[pipebiz] 第%d页采集失败，跳过关键词「%s」', page, keyword)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        time.sleep(self.delay_max * 2)
                        break

                    if len(leads_data) == 0:
                        logger.info('[pipebiz] 关键词="%s" 第%d页无结果，下一关键词', keyword, page)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        break

                    # 4. 保存线索
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    done_pages += 1
                    logger.info('[pipebiz] 关键词="%s" 第%d页: 获取%d条，新增%d条',
                                keyword, page, len(leads_data), new_count)
                    self._progress_update(
                        done_pages=done_pages,
                        collected=total_new,
                        message='关键词「%s」第 %d 页: 新增 %d 条（累计 %d 条）'
                                % (keyword, page, new_count, total_new),
                    )

            # 5. 更新任务状态
            if failed_units:
                error_msg = '以下采集单元失败: ' + '；'.join(failed_units)
                self.update_task(task_id, '失败', result_count=total_new, error_msg=error_msg)
                self._progress_finish('失败', collected=total_new, error_msg=error_msg)
            else:
                self.update_task(task_id, '完成', result_count=total_new)
                self._progress_finish('完成', collected=total_new)
                logger.info('[pipebiz] 采集完成，共新增 %d 条线索', total_new)

            return total_new

        except ScraperStopped:
            logger.info('[pipebiz] 采集已被手动停止，累计新增 %d 条线索', total_new)
            self.update_task(task_id, '已停止', result_count=total_new)
            self._progress_finish('已停止', collected=total_new)
            return total_new

        except Exception as e:
            logger.exception('[pipebiz] 采集异常: %s', e)
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
            logger.error('[pipebiz] 浏览器未启动')
            return None

        # 1. 搜索获取列表页 HTML
        html = self.browser.search_keyword(keyword, page_num=page)
        if not html:
            return None

        # 2. 解析列表页
        leads = parse_search_results(html, self.base_url)
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
                detail_html = self.browser.get_detail(detail_url)
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
                logger.warning('[pipebiz] 详情页解析失败: %s - %s', detail_url, e)

            if dedup_key:
                self._seen_keys.add(dedup_key)

        return leads
