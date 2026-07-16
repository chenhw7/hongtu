# -*- coding: utf-8 -*-
"""爬虫基类：处理HTTP请求、重试、限速、日志"""
import json
import os
import random
import re
import time
import logging
from datetime import datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError

from scraper.utils import safe_filename as _safe_filename_impl

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


class ScraperStopped(Exception):
    """采集被用户主动停止时抛出，用于跳出多层循环。"""
    pass


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
    def fetch(
        self,
        url,
        params=None,
        max_retries=3,
        extra_headers=None,
        return_error_response=False,
    ):
        """发起HTTP请求，带重试和限速

        Args:
            url: 请求URL
            params: 查询参数 dict
            max_retries: 最大重试次数
            extra_headers: 额外/覆盖的请求头（如需要 Accept: application/json 的
                JSON API，会话默认 Accept 头偏向 HTML，需要显式覆盖）
            return_error_response: 为 True 时返回最终的非 200 响应，供调用方区分
                正常 404 翻页结束与其他错误；默认 False 保持原有行为

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

        last_error_response = None
        for attempt in range(1, retries + 1):
            try:
                # 限速：每次请求前随机延迟
                delay = self.get_random_delay()
                time.sleep(delay)

                headers = {'User-Agent': self.get_random_ua()}
                if self.referer:
                    headers['Referer'] = self.referer
                if extra_headers:
                    headers.update(extra_headers)
                logger.info('[%s] 请求第 %d/%d 次: %s', self.source_type, attempt, retries, url)
                response = self.session.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    # 自动检测编码
                    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                        response.encoding = response.charset_encoding or 'utf-8'
                    return response
                else:
                    last_error_response = response
                    logger.warning('[%s] HTTP %d: %s', self.source_type, response.status_code, url)
                    # 被限流时等待更久
                    if response.status_code in (429, 503):
                        wait = self.delay_max * attempt
                        time.sleep(wait)
                    elif response.status_code >= 400:
                        # 客户端/服务端错误，不再重试
                        return response if return_error_response else None

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
        if return_error_response and last_error_response is not None:
            return last_error_response
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

    def fetch_html(self, url, params=None, max_retries=None):
        """发起请求，同时返回原始HTML文本与 BeautifulSoup 对象

        原始文本用于保存网页快照（保留完整原文，便于公告被撤回/修改后追溯）。

        Returns:
            (html_text, soup) 二元组，请求失败时均为 None
        """
        response = self.fetch(url, params=params, max_retries=max_retries)
        if response is None:
            return None, None
        html_text = response.text
        try:
            soup = BeautifulSoup(html_text, 'lxml')
        except Exception:
            soup = BeautifulSoup(html_text, 'html.parser')
        return html_text, soup

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

            # 附件与原始HTML快照单独处理，不写入 raw_data JSON（避免字段冗余膨胀）
            attachments_data = item.get('attachments') or []
            raw_html = item.get('_raw_html')
            raw_data_item = {k: v for k, v in item.items() if k not in ('attachments', '_raw_html')}

            lead = Lead(
                bidding_number=bidding_number or None,
                project_name=project_name,
                announcement_type=item.get('announcement_type', ''),
                buyer_name=buyer_name,
                buyer_address=item.get('buyer_address', ''),
                region=item.get('region', ''),
                contact_person=item.get('contact_person', ''),
                phone=item.get('phone', ''),
                agency_name=item.get('agency_name', ''),
                agency_phone=item.get('agency_phone', ''),
                budget_amount=item.get('budget_amount'),
                publish_date=item.get('publish_date'),
                publish_time=item.get('publish_time'),
                deadline=item.get('deadline'),
                source_url=item.get('source_url', ''),
                source_type=source_type,
                raw_data=json.dumps(raw_data_item, ensure_ascii=False, default=str),
            )
            db.session.add(lead)
            try:
                db.session.commit()
                new_count += 1
            except IntegrityError as exc:
                db.session.rollback()
                if 'unique constraint' in str(exc).lower() or 'duplicate entry' in str(exc).lower():
                    logger.warning(
                        '[%s] 保存线索触发唯一约束，跳过: %s',
                        source_type,
                        item.get('bidding_number', item.get('project_name', '')),
                    )
                    continue
                logger.exception(
                    '[%s] 保存线索发生完整性错误: %s',
                    source_type,
                    item.get('bidding_number', item.get('project_name', '')),
                )
                raise
            except Exception:
                db.session.rollback()
                logger.exception(
                    '[%s] 保存线索发生数据库错误: %s',
                    source_type,
                    item.get('bidding_number', item.get('project_name', '')),
                )
                raise

            # 保存详情页HTML快照：公告在官网被撤回/修改后仍可本地留档追溯
            if raw_html and self._config_flag('SCRAPE_SAVE_SNAPSHOT', True):
                snapshot_path = self._save_snapshot(lead.id, raw_html)
                if snapshot_path:
                    lead.html_snapshot_path = snapshot_path
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            # 下载详情页附件（招标文件/报价单等）
            if attachments_data and self._config_flag('SCRAPE_DOWNLOAD_ATTACHMENTS', True):
                self._save_attachments(lead.id, attachments_data)

        return new_count

    # ------------------------------------------------------------------
    # 网页快照与附件下载
    # ------------------------------------------------------------------
    _UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')

    def _config_flag(self, name, default):
        """读取 app.config 中的配置项，无 app 时返回默认值"""
        if self.app is None:
            return default
        return self.app.config.get(name, default)

    @staticmethod
    def _safe_filename(name, default='attachment'):
        """清理文件名中的路径分隔符等危险字符，防止路径穿越。

        委托给 scraper/utils.py 中的实现，避免重复定义。
        """
        return _safe_filename_impl(name, default)

    def _save_snapshot(self, lead_id, html):
        """保存详情页原始HTML到 instance 目录，返回相对路径"""
        if self.app is None:
            return None
        try:
            snapshot_dir_name = self.app.config.get('SCRAPE_SNAPSHOT_DIR', 'snapshots')
            snap_dir = os.path.join(self.app.instance_path, snapshot_dir_name, self.source_type)
            os.makedirs(snap_dir, exist_ok=True)
            filename = f'{lead_id}.html'
            with open(os.path.join(snap_dir, filename), 'w', encoding='utf-8') as f:
                f.write(html)
            return '/'.join([snapshot_dir_name, self.source_type, filename])
        except Exception as e:
            logger.warning('[%s] 保存网页快照失败(lead=%s): %s', self.source_type, lead_id, e)
            return None

    def _download_file(self, url, dest_path, max_size):
        """流式下载单个文件，超出 max_size 则放弃。返回文件字节数，失败返回 None"""
        if self.session is None:
            self._create_session()
        try:
            headers = {'User-Agent': self.get_random_ua()}
            if self.referer:
                headers['Referer'] = self.referer
            with self.session.stream('GET', url, headers=headers, timeout=60.0) as response:
                if response.status_code != 200:
                    logger.warning('[%s] 附件下载 HTTP %d: %s', self.source_type, response.status_code, url)
                    return None
                total = 0
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > max_size:
                            logger.warning('[%s] 附件超出大小限制(>%d字节)，已放弃: %s',
                                           self.source_type, max_size, url)
                            f.close()
                            try:
                                os.remove(dest_path)
                            except OSError:
                                pass
                            return None
                        f.write(chunk)
                return total
        except Exception as e:
            logger.warning('[%s] 附件下载异常: %s - %s', self.source_type, url, e)
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except OSError:
                pass
            return None

    def _save_attachments(self, lead_id, attachments_data):
        """下载详情页附件并记录到 Attachment 表"""
        from app.models import Attachment
        from app.extensions import db

        max_count = self._config_flag('SCRAPE_ATTACHMENT_MAX_COUNT', 10)
        max_size = self._config_flag('SCRAPE_ATTACHMENT_MAX_SIZE', 20 * 1024 * 1024)
        attach_dir_name = self._config_flag('SCRAPE_ATTACHMENT_DIR', 'attachments')

        for att in attachments_data[:max_count]:
            url = (att.get('url') or '').strip()
            if not url:
                continue
            name = self._safe_filename(att.get('name'))

            record = Attachment(lead_id=lead_id, file_name=name, file_url=url, download_status='待下载')
            db.session.add(record)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                continue

            try:
                dest_dir = os.path.join(self.app.instance_path, attach_dir_name, self.source_type, str(lead_id))
                os.makedirs(dest_dir, exist_ok=True)
                saved_filename = f'{record.id}_{name}'
                dest_path = os.path.join(dest_dir, saved_filename)

                # 附件下载同样保持限速，避免对目标站造成压力
                time.sleep(self.get_random_delay())
                size = self._download_file(url, dest_path, max_size)
                if size is not None:
                    record.local_path = '/'.join([attach_dir_name, self.source_type, str(lead_id), saved_filename])
                    record.file_size = size
                    record.download_status = '成功'
                else:
                    record.download_status = '失败'
                    record.error_msg = '下载失败或超出大小限制'
            except Exception as e:
                record.download_status = '失败'
                record.error_msg = str(e)[:500]
                logger.warning('[%s] 附件下载异常(lead=%s): %s - %s', self.source_type, lead_id, url, e)

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    # ------------------------------------------------------------------
    # 实时进度（内存追踪，失败不影响采集主流程）
    # ------------------------------------------------------------------
    def _progress_start(self, task_id, total_keywords, max_pages):
        try:
            from scraper import progress
            progress.start_progress(self.source_type, task_id, total_keywords, max_pages)
            progress.init_control(self.source_type)
        except Exception:
            logger.debug('[%s] 进度初始化失败（忽略）', self.source_type, exc_info=True)

    def _progress_update(self, **fields):
        try:
            from scraper import progress
            progress.update_progress(self.source_type, **fields)
        except Exception:
            logger.debug('[%s] 进度更新失败（忽略）', self.source_type, exc_info=True)

    def _keyword_display(self, keyword):
        """返回关键词的用户友好显示名称，子类可覆写以自定义展示。"""
        return keyword

    def _progress_finish(self, status, collected=0, error_msg=None):
        try:
            from scraper import progress
            progress.finish_progress(self.source_type, status, collected=collected, error_msg=error_msg)
        except Exception:
            logger.debug('[%s] 进度结束标记失败（忽略）', self.source_type, exc_info=True)

    def _progress_clear_control(self):
        try:
            from scraper import progress
            progress.clear_control(self.source_type)
        except Exception:
            logger.debug('[%s] 控制状态清理失败（忽略）', self.source_type, exc_info=True)

    def _check_pause_and_stop(self):
        """在采集循环的关键节点调用：若已暂停则阻塞等待，若已请求停止则抛出异常跳出采集。"""
        try:
            from scraper import progress
            progress.wait_if_paused(self.source_type)
            if progress.is_stop_requested(self.source_type):
                raise ScraperStopped()
        except ScraperStopped:
            raise
        except Exception:
            logger.debug('[%s] 暂停/停止状态检查失败（忽略）', self.source_type, exc_info=True)

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

        # 初始化实时进度（失败不影响主流程）
        self._progress_start(task_id, len(keywords), max_pages)

        total_new = 0
        done_pages = 0
        failed_units = []
        try:
            self._create_session()

            # 2. 遍历关键词和页数
            for kw_index, keyword in enumerate(keywords, start=1):
                self._check_pause_and_stop()
                self._progress_update(
                    keyword_index=kw_index,
                    current_keyword=keyword,
                    message='采集关键词「%s」(%d/%d)' % (self._keyword_display(keyword), kw_index, len(keywords)),
                )
                for page in range(1, max_pages + 1):
                    self._check_pause_and_stop()
                    logger.info('[%s] 关键词="%s" 第 %d 页', self.source_type, keyword, page)
                    self._progress_update(
                        current_page=page,
                        message='采集关键词「%s」第 %d/%d 页' % (self._keyword_display(keyword), page, max_pages),
                    )
                    leads_data = self._scrape_page(keyword, page)

                    if leads_data is None:
                        # 请求失败或被拦截
                        failed_units.append(
                            '%s 第%d页' % (self._keyword_display(keyword), page)
                        )
                        logger.warning('[%s] 第%d页采集失败，等待%ds后跳过关键词「%s」',
                                       self.source_type, page, self.anti_scrape_wait, keyword)
                        # 跳过该关键词剩余页，计入已完成页数以推进进度
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        if self.anti_scrape_wait > 0:
                            time.sleep(self.anti_scrape_wait)
                        break

                    if len(leads_data) == 0:
                        # 无更多结果
                        logger.info('[%s] 关键词="%s" 第%d页无结果，下一关键词', self.source_type, keyword, page)
                        done_pages += (max_pages - page + 1)
                        self._progress_update(done_pages=done_pages)
                        break

                    # 3. 保存线索
                    new_count = self.save_leads(leads_data, self.source_type)
                    total_new += new_count
                    done_pages += 1
                    logger.info('[%s] 关键词="%s" 第%d页: 获取%d条，新增%d条',
                                self.source_type, keyword, page, len(leads_data), new_count)
                    self._progress_update(
                        done_pages=done_pages,
                        collected=total_new,
                        message='关键词「%s」第 %d 页: 新增 %d 条（累计 %d 条）'
                                % (self._keyword_display(keyword), page, new_count, total_new),
                    )

            # 4. 更新任务状态。允许其他关键词在单个关键词失败后继续采集，但最终
            # 必须如实标记失败，不能把部分缺数的任务显示成“完成”。
            if failed_units:
                error_msg = '以下采集单元失败: ' + '；'.join(failed_units)
                self.update_task(
                    task_id,
                    '失败',
                    result_count=total_new,
                    error_msg=error_msg,
                )
                self._progress_finish('失败', collected=total_new, error_msg=error_msg)
                logger.warning('[%s] 采集部分失败，共新增 %d 条: %s', self.source_type, total_new, error_msg)
            else:
                self.update_task(task_id, '完成', result_count=total_new)
                self._progress_finish('完成', collected=total_new)
                logger.info('[%s] 采集完成，共新增 %d 条线索', self.source_type, total_new)
            return total_new

        except ScraperStopped:
            logger.info('[%s] 采集已被手动停止，累计新增 %d 条线索', self.source_type, total_new)
            self.update_task(task_id, '已停止', result_count=total_new)
            self._progress_finish('已停止', collected=total_new)
            return total_new

        except Exception as e:
            logger.exception('[%s] 采集异常: %s', self.source_type, e)
            self.update_task(task_id, '失败', result_count=total_new, error_msg=str(e))
            self._progress_finish('失败', collected=total_new, error_msg=str(e))
            return total_new
        finally:
            self._close_session()
            self._progress_clear_control()

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果（子类实现）

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict]: 线索列表，None 表示请求失败
        """
        raise NotImplementedError
