# -*- coding: utf-8 -*-
"""广东省公共资源交易平台（粤公平）爬虫 (ygp.gdzwfw.gov.cn)。

模块化结构：
- search.py：搜索 API 调用 + 分页逻辑（POST JSON）
- detail.py：详情 API 调用 + richText HTML 解析
- parser.py：列表项解析（API 响应 -> Lead dict）
- regions.py：广东省 21 地市 siteCode 注册表
- utils.py：ggzyjy 专用工具函数（日期/金额/HTML/电话解析）
"""
import logging
import re

from scraper.base import BaseScraper
from scraper.keywords import GGZYJY_KEYWORDS_FINAL
from scraper.ggzyjy.regions import REGIONS
from scraper.ggzyjy.search import scrape_search_page, scrape_channel_page

logger = logging.getLogger(__name__)

# 伪关键词正则：channel:jsgc, channel:zfcg, channel:jsgc:guangzhou 等
_CHANNEL_KEYWORD_RE = re.compile(r'^channel:(jsgc|zfcg)(?::(\w+))?$')

# 频道中文名（用于进度展示）
_CHANNEL_NAMES = {
    'jsgc': '工程建设',
    'zfcg': '政府采购',
}


class GgzyjyScraper(BaseScraper):
    """广东省公共资源交易平台（粤公平）爬虫。

    API 地址: https://ygp.gdzwfw.gov.cn/ggzy-portal/search/v2/items (POST)

    支持三种采集模式：
    1. 关键词搜索：直接传文本关键词（如 "管道"、"给排水工程"）
    2. 频道浏览：伪关键词 "channel:jsgc"（工程建设全省）、"channel:zfcg"（政府采购全省）
    3. 地市频道：伪关键词 "channel:jsgc:guangzhou"（广州市工程建设）
    """

    source_type = 'ggzyjy'
    base_url = 'https://ygp.gdzwfw.gov.cn'
    referer = 'https://ygp.gdzwfw.gov.cn/'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.ggzyjy_keywords = list(GGZYJY_KEYWORDS_FINAL)

    def default_keywords(self):
        """生成默认关键词列表：搜索关键词 + 频道伪关键词。

        搜索关键词约 40 个 + 2 个全省频道 ≈ 42 个采集单元。
        """
        keywords = list(self.ggzyjy_keywords)
        # 全省频道：工程建设 + 政府采购
        keywords.append('channel:jsgc')
        keywords.append('channel:zfcg')
        return keywords

    def _keyword_display(self, keyword):
        """将伪关键词转换为用户友好名称用于进度展示。"""
        m = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if m:
            channel = m.group(1)
            region_code = m.group(2)
            channel_name = _CHANNEL_NAMES.get(channel, channel)
            if region_code:
                region = REGIONS.get(region_code)
                region_name = region['name'] if region else region_code
                return f'{channel_name}·{region_name}'
            return f'{channel_name}（全省）'
        return keyword

    def _scrape_page(self, keyword, page):
        """采集单页。根据关键词类型分发到搜索或频道采集。"""
        # 按关键词类型控制最大页数
        kw_max = getattr(self, '_kw_max_pages', {}).get(keyword, 5)
        if page > kw_max:
            return []  # 返回空列表，触发基类的翻页终止逻辑

        channel_match = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if channel_match:
            channel = channel_match.group(1)
            region_code = channel_match.group(2) or None
            return scrape_channel_page(self, channel, page, region_code=region_code)

        # 普通关键词 → 搜索采集
        return scrape_search_page(self, keyword, page)

    def run(self, keywords=None, max_pages=None):
        """执行采集。

        关键词搜索默认 max_pages=5，频道采集默认 max_pages=2。
        """
        if keywords is None:
            keywords = self.default_keywords()

        if max_pages is None:
            # 记录每个关键词的最大页数，在 _scrape_page 中用于提前终止
            self._kw_max_pages = {}
            for kw in keywords:
                self._kw_max_pages[kw] = 2 if kw.startswith('channel:') else 5
            # 统一用最大页数 5，_scrape_page 内部按关键词类型提前终止
            return super().run(keywords=keywords, max_pages=5)

        return super().run(keywords=keywords, max_pages=max_pages)
