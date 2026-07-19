# -*- coding: utf-8 -*-
"""广东省住建厅（广东建设信息网 skypt.gdcic.net）采集模块。

数据开放平台 API 完全开放、无需签名/Token，可直接 httpx 调用。

模块结构：
- api.py：   开放平台 API 调用封装（列表+详情+项目信息）
- parser.py：API JSON 响应 → Lead dict 字段映射
- utils.py： gdcic 专用工具函数（日期/文本清理）
"""
import logging

from scraper.base import BaseScraper
from scraper.keywords import PLATFORM_KEYWORDS_FINAL
from scraper.gdcic.api import (
    fetch_bidding_list,
    fetch_bidding_detail,
    fetch_project_info,
)
from scraper.gdcic.parser import (
    parse_bidding_list_item,
    parse_bidding_detail,
    parse_project_info,
)

logger = logging.getLogger(__name__)


class GdcicScraper(BaseScraper):
    """广东住建厅采集器。

    继承 BaseScraper 以复用 save_leads()、进度追踪、暂停/停止等功能。
    通过 httpx 直调开放平台 API 获取招投标数据，无需 Playwright。
    """

    source_type = 'gdcic'
    base_url = 'https://skypt.gdcic.net'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(PLATFORM_KEYWORDS_FINAL)
        # 开放平台 API 限速：2-3 秒/请求，避免触发风控
        self.delay_min = 2
        self.delay_max = 3
        # API 模式无需 60s 反爬等待（与 gzfcj/ggzyjy 对齐）
        self.anti_scrape_wait = 0

    def _scrape_page(self, keyword, page):
        """采集单页招投标搜索结果。

        流程：
        1. 调用列表 API 获取招投标列表
        2. 解析列表项为 Lead dict（列表中部分字段为 null）
        3. 前置去重：跳过已存在线索的详情请求
        4. 调用详情 API 补全 address/biddingDate/biddingMoney/scale/
           biddingUnitPerson 等字段；详情失败不入库（方案 A：下次 run 重试）
        5. 详情成功后调用项目信息 API 补全 buildUnit/totalInvest/
           project_location 等字段

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict] or None: 线索列表（详情失败的条目已移除），
            None 表示列表请求失败
        """
        # 1. 调用列表 API
        payload = fetch_bidding_list(self, keyword=keyword, page_num=page)
        if payload is None:
            return None

        rows = payload.get('rows') or []
        if not rows:
            logger.info('[gdcic] 关键词="%s" 第%d页无结果', keyword, page)
            return []

        # 2. 解析列表项
        leads = []
        for row in rows:
            lead = parse_bidding_list_item(row)
            if lead.get('project_name'):
                leads.append(lead)

        if not leads:
            return []

        logger.info('[gdcic] 列表解析: %d 行 → %d 条有效线索', len(rows), len(leads))

        # 3. 前置去重：批量预查已存在的线索，跳过详情请求
        existing_keys = self._prefetch_existing_keys(leads)
        skipped = 0
        detail_failed = 0
        valid_leads = []

        # 4. 调用详情 API 补全字段；5. 详情成功后调用项目信息 API
        for lead in leads:
            self._check_pause_and_stop()

            # pop 临时字段（无论是否请求详情都要移除）
            bidding_id = lead.pop('_bidding_id', '')

            # 已存在的线索跳过详情请求，保留列表字段
            key = self._lead_dedup_key(lead)
            if key and key in existing_keys:
                skipped += 1
                valid_leads.append(lead)
                continue

            # 调用详情 API 补全字段
            if bidding_id:
                detail = fetch_bidding_detail(self, bidding_id)
                detail_fields = parse_bidding_detail(detail) if detail else {}
                if not detail_fields:
                    # 详情失败或解析无有效字段：不入库残缺数据（方案 A），
                    # 下次 run 时该记录不会被去重命中，会重新请求详情
                    detail_failed += 1
                    logger.warning(
                        '[gdcic] 详情失败，跳过该条，下次 run 会重试: '
                        'bidding_id=%s project=%s',
                        bidding_id, lead.get('project_name', ''))
                    continue
                lead.update(detail_fields)

                # 详情成功后调用项目信息 API 补充建设单位/总投资/项目所在地等
                project_code = lead.get('project_code', '')
                if project_code:
                    project_info = fetch_project_info(self, project_code)
                    if project_info:
                        project_fields = parse_project_info(project_info)
                        if project_fields:
                            lead.update(project_fields)

            valid_leads.append(lead)
            # 计入进程内缓存，避免同次 run 内重复请求详情
            if key:
                self._seen_keys.add(key)

        if skipped:
            logger.info('[gdcic] 跳过 %d 条已存在项的详情请求', skipped)
        if detail_failed:
            logger.warning(
                '[gdcic] %d 条详情失败已跳过，下次 run 会重试', detail_failed)

        return valid_leads
