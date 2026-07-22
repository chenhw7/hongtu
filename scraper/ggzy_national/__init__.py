# -*- coding: utf-8 -*-
"""全国公共资源交易平台采集模块 (www.ggzy.gov.cn)。

全国平台聚合 31 省 + 新疆兵团 + 央企/部委数据，一个源即可覆盖全国公共资源交易
公告。部署阿里云 WAF，裸 HTTP 请求会被强制关闭 TCP 连接，需先用 Playwright
建立会话取得 Cookie，再由 httpx 携带 Cookie 调用 getTradList 接口。

模块结构：
- api.py：列表接口 + WAF Cookie 管理（Playwright + httpx 自动回退）
- parser.py：getTradList 响应记录 → Lead dict
- detail.py：/b/ 正文页 HTML 解析（联系人/电话/预算/资质/开标时间等）
- regions.py：31 省 + 兵团行政区划码（DEAL_PROVINCE 过滤）
- utils.py：日期/预算/电话解析

伪关键词：
- channel:national            — 全国拉取（默认，不按省份过滤）
- channel:province:guangdong   — 按省份定向（slug 见 regions.py:REGION_CODES）

详见 docs/数据源扩展-可行性调研实施报告.md 第三章。
"""
import logging
import re

from scraper.base import BaseScraper
from scraper.ggzy_national.api import GgzyNationalApi
from scraper.ggzy_national.regions import REGION_CODES

logger = logging.getLogger(__name__)

# 伪关键词：channel:national 或 channel:province:<slug>
_CHANNEL_RE = re.compile(r'^channel:(national|province(?::(\w+))?)$')

# 省份 slug -> 中文名（用于 UI 显示）
# 复用 ccgp/regions.py 的省名取值，避免额外维护一份省名表
from scraper.ccgp.regions import REGIONS as _CCGP_REGIONS  # noqa: E402

_PROVINCE_NAMES = {
    slug: info['name']
    for slug, info in _CCGP_REGIONS.items()
    if isinstance(info, dict) and 'name' in info
}


class GgzyNationalScraper(BaseScraper):
    """全国公共资源交易平台采集器。

    Playwright 获取 WAF Cookie 后，httpx 调用 getTradList（关键词 × 时间/省份
    三维过滤），对每条记录请求 /b/ 正文页解析详情。
    """

    source_type = 'ggzy_national'
    base_url = 'https://www.ggzy.gov.cn'
    referer = 'https://www.ggzy.gov.cn/deal/dealList.html'

    def __init__(self, app=None):
        super().__init__(app=app)
        self._api = None
        # 复用 ggzyjy 系关键词（产品词+工程词+项目词，去重后的最终列表）
        from scraper.keywords import GGZYJY_KEYWORDS_FINAL
        self._keywords = list(GGZYJY_KEYWORDS_FINAL)

    def default_keywords(self):
        """默认采集单元：关键词搜索 + 全国频道。

        关键词约 40 个（来自 GGZYJY_KEYWORDS_FINAL）+ 全国频道 1 个 ≈ 41 个采集单元。
        省份定向为按需补充，默认不纳入，避免与全国拉取重复。
        """
        keywords = list(self._keywords)
        keywords.append('channel:national')
        return keywords

    def _keyword_display(self, keyword):
        """伪关键词 -> 用户友好名称。"""
        m = _CHANNEL_RE.match(keyword or '')
        if m:
            if m.group(1) == 'national':
                return '全国公共资源交易'
            slug = m.group(2)
            name = _PROVINCE_NAMES.get(slug, slug)
            return f'全国平台·{name}'
        return keyword

    def _init_api(self):
        """初始化 API 客户端（懒加载）。

        全国平台 WAF 对裸 httpx 的拦截具波动性：实测裸 httpx 常可直接访问，
        故不预先启动 Playwright 获取 Cookie。当请求被 WAF 拦截（403/连接关闭）
        时，api.py 的 _post_form/fetch_detail_html 会自动调用 refresh_cookies()
        重建 Playwright 会话并重试。
        """
        if self._api is None:
            self._api = GgzyNationalApi(cookies_str='')
        return self._api

    def _scrape_page(self, keyword, page):
        """采集单页，按关键词类型分发。

        Args:
            keyword: 搜索关键词或伪关键词（channel:national / channel:province:xxx）
            page: 页码（从 1 开始）

        Returns:
            list[dict] or None: 线索列表；None 表示请求失败
        """
        api = self._init_api()

        channel_match = _CHANNEL_RE.match(keyword or '')
        if channel_match:
            province = ''
            if channel_match.group(1) == 'province':
                slug = channel_match.group(2)
                province = REGION_CODES.get(slug, '')
                if not province:
                    logger.warning('[ggzy_national] 未知省份 slug: %s', slug)
                    return []
            # 频道模式：不按关键词过滤，按省份/全国浏览
            return self._scrape_channel(api, province, page)

        # 普通关键词：全国范围搜索
        return self._scrape_by_keyword(api, keyword, page)

    def _scrape_by_keyword(self, api, keyword, page):
        """关键词搜索模式（全国范围）。"""
        leads, has_more = api.fetch_list(keyword=keyword, page=page)
        if leads is None:
            return None
        return self._process_leads(api, leads)

    def _scrape_channel(self, api, province, page):
        """频道浏览模式（不按关键词，全国或指定省份）。"""
        leads, has_more = api.fetch_list(keyword='', page=page, province=province)
        if leads is None:
            return None
        return self._process_leads(api, leads)

    def _process_leads(self, api, leads):
        """处理线索列表：前置去重 + 请求 /b/ 详情补充字段。"""
        if not leads:
            return []

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

            detail_path = lead.pop('_detail_path', '')
            lead.pop('_business_type', '')
            lead.pop('_information_type', '')
            if detail_path:
                from scraper.ggzy_national.detail import fetch_detail
                detail_data = fetch_detail(self, api, detail_path)
                if detail_data:
                    lead.update(detail_data)
            detailed_leads.append(lead)

        if skipped:
            logger.info('[ggzy_national] 跳过 %d 条已存在项的详情请求', skipped)

        return detailed_leads

    def run(self, keywords=None, max_pages=None):
        """执行采集。

        关键词搜索默认 max_pages=5；频道（全国/省份浏览）默认 max_pages=3。
        """
        if keywords is None:
            keywords = self.default_keywords()

        if max_pages is None:
            self._kw_max_pages = {}
            for kw in keywords:
                self._kw_max_pages[kw] = 3 if kw.startswith('channel:') else 5
            return super().run(keywords=keywords, max_pages=5)

        return super().run(keywords=keywords, max_pages=max_pages)
