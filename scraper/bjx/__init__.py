# -*- coding: utf-8 -*-
"""北极星环保网（bjx.com.cn）采集模块。

采用 www.bjx.com.cn 主站搜索通道（无 WAF）+ 纯 httpx 策略：
- 主站搜索 URL：https://www.bjx.com.cn/search/?kw={keyword}
- 每关键词返回 20 条最新结果（无分页，服务端忽略 page 参数）
- 不需要 Playwright、Cookie、滑块验证

模块结构：
- parser.py:  HTML DOM 解析 → Lead dict
- utils.py:   请求头构建、文本清理
"""
import logging
import random
import time
import urllib.parse

import httpx

from scraper.base import BaseScraper, ScraperStopped
from scraper.keywords import BJX_KEYWORDS_FINAL
from scraper.bjx.parser import parse_search_page

logger = logging.getLogger(__name__)


class BjxScraper(BaseScraper):
    """北极星环保网采集器。

    继承 BaseScraper 以复用 save_leads()、进度追踪、暂停/停止等功能。
    使用 www.bjx.com.cn 主站搜索接口，纯 httpx 请求，无需浏览器。
    """

    source_type = 'bjx'
    base_url = 'https://www.bjx.com.cn'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(BJX_KEYWORDS_FINAL)
        # 限速配置（秒）
        self.delay_min = 1.5
        self.delay_max = 3.0
        # httpx 客户端
        self._http_client = None

    def run(self, keywords=None, max_pages=5):
        """执行采集。

        流程：
        1. 创建 httpx 客户端
        2. 遍历关键词，请求 www.bjx.com.cn/search/?kw={kw}
        3. 解析列表页提取线索（含标题过滤）
        4. 保存有效线索

        Args:
            keywords: 关键词列表，None 时使用 BJX_KEYWORDS_FINAL
            max_pages: 兼容参数（主站搜索无分页，实际每关键词固定 20 条）

        Returns:
            int: 新增线索数量
        """
        if keywords is None:
            keywords = self.keywords

        logger.info('[bjx] 开始采集，关键词: %s，共 %d 个', keywords[:3], len(keywords))

        # 1. 创建任务记录
        task = self.create_task(self.source_type, self.base_url)
        task_id = task.id

        # 初始化实时进度（每关键词 1 页，因为主站搜索无分页）
        self._progress_start(task_id, len(keywords), 1)

        total_new = 0
        done_pages = 0
        failed_units = []
        self._seen_keys = set()

        try:
            # 2. 创建 httpx 客户端
            self._create_http_client()

            # 3. 遍历关键词
            for kw_index, keyword in enumerate(keywords, start=1):
                self._check_pause_and_stop()
                self._progress_update(
                    keyword_index=kw_index,
                    current_keyword=keyword,
                    current_page=1,
                    message='采集关键词「%s」(%d/%d)' % (keyword, kw_index, len(keywords)),
                )

                leads_data = self._scrape_keyword(keyword)

                if leads_data is None:
                    failed_units.append(keyword)
                    logger.warning('[bjx] 关键词「%s」采集失败', keyword)
                elif len(leads_data) == 0:
                    logger.info('[bjx] 关键词="%s" 无有效结果', keyword)
                else:
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    logger.info('[bjx] 关键词="%s": 获取%d条，新增%d条',
                                keyword, len(leads_data), new_count)

                done_pages += 1
                self._progress_update(
                    done_pages=done_pages,
                    collected=total_new,
                    message='关键词「%s」: 新增 %d 条（累计 %d 条）'
                            % (keyword, len(leads_data) if leads_data else 0, total_new),
                )

                # 限速
                time.sleep(random.uniform(self.delay_min, self.delay_max))

            # 4. 更新任务状态
            if failed_units:
                error_msg = '以下关键词采集失败: ' + '、'.join(failed_units)
                self.update_task(task_id, '完成', result_count=total_new, error_msg=error_msg)
                self._progress_finish('完成', collected=total_new, error_msg=error_msg)
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
            self._close_http_client()
            self._progress_clear_control()

    def _create_http_client(self):
        """创建 httpx 客户端。"""
        self._close_http_client()
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/126.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Referer': 'https://www.bjx.com.cn/',
            },
        )

    def _close_http_client(self):
        """关闭 httpx 客户端。"""
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None

    def _scrape_keyword(self, keyword):
        """采集单个关键词的搜索结果。

        请求 https://www.bjx.com.cn/search/?kw={keyword}，解析列表页。

        Args:
            keyword: 搜索关键词

        Returns:
            list[dict]: 线索列表，None 表示请求失败
        """
        kw_encoded = urllib.parse.quote(keyword)
        url = f'https://www.bjx.com.cn/search/?kw={kw_encoded}'

        html = self._http_get(url)
        if not html:
            return None

        # 解析搜索结果
        leads = parse_search_page(html)
        if not leads:
            return []

        # 进程内去重
        unique_leads = []
        for lead in leads:
            dedup_key = self._lead_dedup_key(lead)
            if dedup_key and dedup_key in self._seen_keys:
                continue
            if dedup_key:
                self._seen_keys.add(dedup_key)
            unique_leads.append(lead)

        return unique_leads

    def _http_get(self, url, max_retries=3):
        """使用 httpx 发起 GET 请求，带重试。

        Args:
            url: 请求 URL
            max_retries: 最大重试次数

        Returns:
            str: 响应 HTML，失败返回 None
        """
        for attempt in range(1, max_retries + 1):
            try:
                response = self._http_client.get(url)

                if response.status_code == 200:
                    return response.text

                logger.warning('[bjx] HTTP %d: %s (attempt %d)',
                               response.status_code, url, attempt)

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
