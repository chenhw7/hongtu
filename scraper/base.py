# -*- coding: utf-8 -*-
"""爬虫基类：处理HTTP请求、重试、限速、日志"""
import json
import random
import time
import logging
from datetime import datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 随机 User-Agent 池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.69',
]


class BaseScraper:
    """爬虫基类：请求、重试、限速、日志

    子类需实现:
        parse(html)         — 解析搜索结果列表页，返回线索列表
        _parse_detail(soup) — 解析详情页，补充字段（可选）
    """

    # 子类覆盖
    source_type = 'base'
    base_url = ''
    referer = ''  # 子类可覆盖，设置来源页面

    def __init__(self, app=None):
        self.app = app
        self.session = None
        self._robots_cache = {}  # 域名 -> RobotFileParser
        if app is not None:
            self.delay_min = app.config.get('SCRAPE_DELAY_MIN', 3)
            self.delay_max = app.config.get('SCRAPE_DELAY_MAX', 5)
            self.max_retries = app.config.get('SCRAPE_MAX_RETRIES', 3)
            self.keywords = app.config.get('SCRAPER_KEYWORDS', [])
            self.check_robots = app.config.get('SCRAPE_CHECK_ROBOTS', False)
            self.anti_scrape_wait = app.config.get('SCRAPE_ANTI_SCRAPE_WAIT', 60)
        else:
            self.delay_min = 3
            self.delay_max = 5
            self.max_retries = 3
            self.keywords = []
            self.check_robots = False
            self.anti_scrape_wait = 60

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def get_random_delay(self):
        """返回 3-5 秒随机延迟"""
        return random.uniform(self.delay_min, self.delay_max)

    def get_random_ua(self):
        """返回随机 User-Agent"""
        return random.choice(USER_AGENTS)

    def _check_robots(self, url):
        """检查 URL 是否被 robots.txt 允许采集

        Args:
            url: 待采集的 URL

        Returns:
            bool: True 表示允许采集，False 表示被禁止
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # 缓存 robots.txt 解析结果
        if domain not in self._robots_cache:
            rp = RobotFileParser()
            robots_url = f"{domain}/robots.txt"
            rp.set_url(robots_url)
            try:
                rp.read()
                self._robots_cache[domain] = rp
                logger.info('[%s] 已加载 robots.txt: %s', self.source_type, robots_url)
            except Exception as e:
                logger.warning('[%s] 无法获取 robots.txt (%s): %s，默认允许采集',
                               self.source_type, robots_url, e)
                self._robots_cache[domain] = None

        rp = self._robots_cache[domain]
        if rp is None:
            return True

        ua = self.get_random_ua()
        allowed = rp.can_fetch(ua, url)
        if not allowed:
            logger.warning('[%s] robots.txt 禁止采集: %s', self.source_type, url)
        return allowed

    def _create_session(self):
        """创建 httpx 客户端"""
        self.session = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            },
        )

    def _close_session(self):
        """关闭 httpx 客户端"""
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------
    def fetch(self, url, params=None, max_retries=3):
        """发起HTTP请求，带重试和限速

        Args:
            url: 请求URL
            params: 查询参数 dict
            max_retries: 最大重试次数

        Returns:
            httpx.Response 或 None
        """
        if self.session is None:
            self._create_session()

        # 合规检查：遵守 robots.txt 协议
        if self.check_robots and not self._check_robots(url):
            logger.warning('[%s] robots.txt 禁止采集，跳过: %s', self.source_type, url)
            return None

        retries = max_retries if max_retries else self.max_retries

        for attempt in range(1, retries + 1):
            try:
                # 限速：每次请求前随机延迟
                delay = self.get_random_delay()
                time.sleep(delay)

                headers = {'User-Agent': self.get_random_ua()}
                if self.referer:
                    headers['Referer'] = self.referer
                logger.info('[%s] 请求第 %d/%d 次: %s', self.source_type, attempt, retries, url)
                response = self.session.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    # 自动检测编码
                    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                        response.encoding = response.charset_encoding or 'utf-8'
                    return response
                else:
                    logger.warning('[%s] HTTP %d: %s', self.source_type, response.status_code, url)
                    # 被限流时等待更久
                    if response.status_code in (429, 503):
                        wait = self.delay_max * attempt
                        time.sleep(wait)
                    elif response.status_code >= 400:
                        # 客户端/服务端错误，不再重试
                        return None

            except httpx.TimeoutException:
                logger.warning('[%s] 请求超时 (第%d次): %s', self.source_type, attempt, url)
            except httpx.ConnectError:
                logger.warning('[%s] 连接失败 (第%d次): %s', self.source_type, attempt, url)
            except httpx.HTTPError as e:
                logger.warning('[%s] HTTP错误 (第%d次): %s - %s', self.source_type, attempt, url, e)
            except Exception as e:
                logger.error('[%s] 未知异常 (第%d次): %s - %s', self.source_type, attempt, url, e)

            # 指数退避
            if attempt < retries:
                backoff = 2 ** attempt
                logger.info('[%s] 等待 %d 秒后重试...', self.source_type, backoff)
                time.sleep(backoff)

        logger.error('[%s] 请求最终失败，已达最大重试次数: %s', self.source_type, url)
        return None

    def fetch_soup(self, url, params=None, max_retries=None):
        """发起请求并返回 BeautifulSoup 对象"""
        response = self.fetch(url, params=params, max_retries=max_retries)
        if response is None:
            return None
        try:
            return BeautifulSoup(response.text, 'lxml')
        except Exception:
            return BeautifulSoup(response.text, 'html.parser')

    # ------------------------------------------------------------------
    # 解析（子类实现）
    # ------------------------------------------------------------------
    def parse(self, soup):
        """解析搜索结果列表页HTML

        Args:
            soup: BeautifulSoup 对象

        Returns:
            list[dict]: 线索数据列表
        """
        raise NotImplementedError

    def _parse_detail(self, soup):
        """解析详情页，返回补充字段（子类可选实现）

        Returns:
            dict: 补充字段
        """
        return {}

    # ------------------------------------------------------------------
    # 数据库操作
    # ------------------------------------------------------------------
    def create_task(self, task_type, target_url):
        """创建 ScrapeTask 记录

        Returns:
            ScrapeTask 对象
        """
        from app.models import ScrapeTask
        from app.extensions import db

        task = ScrapeTask(
            task_type=task_type,
            status='运行中',
            target_url=target_url,
            started_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        return task

    def update_task(self, task_id, status, result_count=0, error_msg=None):
        """更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态（完成/失败）
            result_count: 采集数量
            error_msg: 错误信息
        """
        from app.models import ScrapeTask
        from app.extensions import db

        task = db.session.get(ScrapeTask, task_id)
        if task is None:
            logger.error('任务不存在: %s', task_id)
            return

        task.status = status
        task.result_count = result_count
        task.finished_at = datetime.now()
        if error_msg:
            task.error_msg = str(error_msg)[:2000]
        db.session.commit()

    def save_leads(self, leads_data, source_type):
        """保存线索到数据库，按 bidding_number 去重

        Args:
            leads_data: 线索字典列表
            source_type: 来源类型

        Returns:
            int: 新增数量
        """
        from app.models import Lead
        from app.extensions import db

        new_count = 0
        for item in leads_data:
            bidding_number = (item.get('bidding_number') or '').strip()
            project_name = (item.get('project_name') or '').strip()
            buyer_name = (item.get('buyer_name') or '').strip()

            # 去重：优先按招标编号
            if bidding_number:
                existing = Lead.query.filter_by(bidding_number=bidding_number).first()
                if existing:
                    logger.debug('[%s] 跳过已存在: %s', source_type, bidding_number)
                    continue
            elif project_name:
                # 无编号时按 项目名+采购单位 去重
                existing = Lead.query.filter_by(
                    project_name=project_name, buyer_name=buyer_name
                ).first()
                if existing:
                    continue

            lead = Lead(
                bidding_number=bidding_number or None,
                project_name=project_name,
                buyer_name=buyer_name,
                contact_person=item.get('contact_person', ''),
                phone=item.get('phone', ''),
                budget_amount=item.get('budget_amount'),
                publish_date=item.get('publish_date'),
                deadline=item.get('deadline'),
                source_url=item.get('source_url', ''),
                source_type=source_type,
                raw_data=json.dumps(item, ensure_ascii=False, default=str),
            )
            db.session.add(lead)
            try:
                db.session.commit()
                new_count += 1
            except Exception:
                db.session.rollback()
                logger.warning('[%s] 保存线索失败（可能重复）: %s', source_type, item.get('bidding_number', item.get('project_name', '')))
                continue

        return new_count

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self, keywords=None, max_pages=5):
        """执行爬虫主流程

        Args:
            keywords: 关键词列表，为 None 时使用配置中的默认关键词
            max_pages: 每个关键词最多采集页数

        Returns:
            int: 新增线索数量
        """
        if keywords is None:
            keywords = self.keywords

        logger.info('[%s] 开始采集，关键词: %s，每词最多 %d 页', self.source_type, keywords, max_pages)

        # 1. 创建任务记录
        task = self.create_task(self.source_type, self.base_url)
        task_id = task.id

        total_new = 0
        try:
            self._create_session()

            # 2. 遍历关键词和页数
            for keyword in keywords:
                for page in range(1, max_pages + 1):
                    logger.info('[%s] 关键词="%s" 第 %d 页', self.source_type, keyword, page)
                    leads_data = self._scrape_page(keyword, page)

                    if leads_data is None:
                        # 请求失败或被拦截
                        logger.warning('[%s] 第%d页采集失败，等待%ds后跳过关键词「%s」',
                                       self.source_type, page, self.anti_scrape_wait, keyword)
                        time.sleep(self.anti_scrape_wait)
                        break

                    if len(leads_data) == 0:
                        # 无更多结果
                        logger.info('[%s] 关键词="%s" 第%d页无结果，下一关键词', self.source_type, keyword, page)
                        break

                    # 3. 保存线索
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    logger.info('[%s] 关键词="%s" 第%d页: 获取%d条，新增%d条',
                                self.source_type, keyword, page, len(leads_data), new_count)

            # 4. 更新任务状态
            self.update_task(task_id, '完成', result_count=total_new)
            logger.info('[%s] 采集完成，共新增 %d 条线索', self.source_type, total_new)
            return total_new

        except Exception as e:
            logger.exception('[%s] 采集异常: %s', self.source_type, e)
            self.update_task(task_id, '失败', result_count=total_new, error_msg=str(e))
            return total_new
        finally:
            self._close_session()

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果（子类实现）

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict]: 线索列表，None 表示请求失败
        """
        raise NotImplementedError
