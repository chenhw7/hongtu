# -*- coding: utf-8 -*-
"""发改委项目审批公示采集模块 (tzxm.gd.gov.cn)。

模块化结构：
- api.py：API 调用封装（列表+详情，带 JSL Cookie 管理）
- parser.py：响应数据 → Lead dict 字段映射
- utils.py：fdtz 专用工具函数（日期/投资金额解析）

支持 4 种分类：
- 备案项目（ba）：selectByPageBA, flag=1
- 核准项目（hz_gs/hz_gg）：selectHzByPage, flag=9/10
- 审批项目（sp_gs/spz_gg）：selectByPageSP, flag=6/7
- 节能审查（jn）：selectJnscByPage, flag=13

伪关键词：
- channel:ba — 备案项目（全省，不按关键词过滤）
- channel:hz — 核准公告（全省）
- channel:sp — 审批公告（全省）
"""
import logging
import re

from scraper.base import BaseScraper
from scraper.fdtz.api import FdtzApi
from scraper.fdtz.parser import CATEGORY_FLAGS

logger = logging.getLogger(__name__)

# 伪关键词正则：channel:ba, channel:hz, channel:sp, channel:jn
_CHANNEL_KEYWORD_RE = re.compile(r'^channel:(ba|hz|sp|jn)$')

_CHANNEL_NAMES = {
    'ba': '备案项目',
    'hz': '核准项目',
    'sp': '审批项目',
    'jn': '节能审查',
}

# 频道对应的 (category, flag) 列表（一个频道可能包含公示+公告）
_CHANNEL_CATEGORIES = {
    'ba': [('ba', CATEGORY_FLAGS['ba'])],
    'hz': [('hz_gg', CATEGORY_FLAGS['hz_gg'])],   # 核准公告
    'sp': [('sp_gg', CATEGORY_FLAGS['sp_gg'])],   # 审批公告
    'jn': [('jn', CATEGORY_FLAGS['jn'])],
}


class FdtzScraper(BaseScraper):
    """发改委项目审批公示采集器 (tzxm.gd.gov.cn)。

    使用 Playwright 获取 JSL Cookie 后，httpx 携带 Cookie 调用 JSON API。
    """

    source_type = 'fdtz'
    base_url = 'https://tzxm.gd.gov.cn'

    def __init__(self, app=None):
        super().__init__(app=app)
        self._api = None
        # 使用 EIA 关键词（项目类型词为主，适合审批类数据）
        from scraper.keywords import EIA_KEYWORDS_FINAL
        self._keywords = list(EIA_KEYWORDS_FINAL)

    def default_keywords(self):
        """默认关键词：项目类型搜索词 + 频道伪关键词。

        项目类型词（污水处理厂、综合管廊等）约 12 个 + 3 个频道 ≈ 15 个采集单元。
        """
        keywords = list(self._keywords)
        # 添加频道伪关键词（全省不按关键词过滤的浏览模式）
        keywords.extend(['channel:ba', 'channel:hz', 'channel:sp'])
        return keywords

    def _keyword_display(self, keyword):
        """将伪关键词转换为用户友好名称。"""
        m = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if m:
            channel = m.group(1)
            return _CHANNEL_NAMES.get(channel, channel)
        return keyword

    def _init_api(self):
        """初始化 API 客户端（懒加载，首次调用时用 Playwright 获取 Cookie）。"""
        if self._api is None:
            from scraper.playwright_utils import extract_cookies_for_domain

            logger.info('[fdtz] 首次初始化，使用 Playwright 获取 JSL Cookie...')
            cookies_str = extract_cookies_for_domain(self.base_url, wait_seconds=5)
            self._api = FdtzApi(cookies_str=cookies_str)
        return self._api

    def _scrape_page(self, keyword, page):
        """采集单页，根据关键词类型分发到不同采集模式。

        Args:
            keyword: 搜索关键词或伪关键词（channel:ba/hz/sp）
            page: 页码

        Returns:
            list[dict] or None: 线索列表；None 表示请求失败
        """
        api = self._init_api()

        channel_match = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if channel_match:
            return self._scrape_channel(api, channel_match.group(1), page)

        # 普通关键词：依次搜索各分类
        return self._scrape_by_keyword(api, keyword, page)

    def _scrape_channel(self, api, channel, page):
        """频道模式采集（不按关键词过滤，全省浏览）。"""
        categories = _CHANNEL_CATEGORIES.get(channel, [])
        if not categories:
            return []

        all_leads = []
        for category, flag in categories:
            leads, has_more = api.fetch_list(category, flag, page)
            if leads is None:
                return None  # 请求失败
            all_leads.extend(leads)

        return self._process_leads(api, all_leads)

    def _scrape_by_keyword(self, api, keyword, page):
        """关键词搜索模式：同时搜索备案/核准/审批三个分类。"""
        all_leads = []

        # 搜索所有分类
        search_categories = [
            ('ba', CATEGORY_FLAGS['ba']),
            ('hz_gg', CATEGORY_FLAGS['hz_gg']),
            ('sp_gg', CATEGORY_FLAGS['sp_gg']),
        ]
        for category, flag in search_categories:
            leads, has_more = api.fetch_list(category, flag, page, keyword=keyword)
            if leads is None:
                # 单项失败不终止其他分类
                logger.warning('[fdtz] 分类 %s 关键词 "%s" 第 %d 页请求失败',
                               category, keyword, page)
                continue
            all_leads.extend(leads)

        if not all_leads:
            return []

        return self._process_leads(api, all_leads)

    def _process_leads(self, api, leads):
        """处理线索列表：前置去重 + 请求详情补充字段。"""
        if not leads:
            return []

        # 前置去重
        existing_keys = self._prefetch_existing_keys(leads)
        detailed_leads = []
        skipped = 0

        for lead in leads:
            self._check_pause_and_stop()
            key = self._lead_dedup_key(lead)
            if key and key in existing_keys:
                skipped += 1
                detailed_leads.append(lead)
                continue

            # 请求详情
            item_id = lead.pop('_item_id', '')
            category = lead.pop('_category', '')
            if item_id and category:
                detail = api.fetch_detail(category, item_id)
                if detail:
                    lead.update(detail)
            detailed_leads.append(lead)

        if skipped:
            logger.info('[fdtz] 跳过 %d 条已存在项的详情请求', skipped)

        return detailed_leads

    def run(self, keywords=None, max_pages=None):
        """执行采集。

        关键词搜索默认 max_pages=3，频道采集默认 max_pages=2。
        """
        if keywords is None:
            keywords = self.default_keywords()

        if max_pages is None:
            self._kw_max_pages = {}
            for kw in keywords:
                self._kw_max_pages[kw] = 2 if kw.startswith('channel:') else 3
            return super().run(keywords=keywords, max_pages=3)

        return super().run(keywords=keywords, max_pages=max_pages)
