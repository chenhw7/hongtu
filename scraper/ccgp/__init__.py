# -*- coding: utf-8 -*-
"""中国政府采购网爬虫 (ccgp.gov.cn)。

模块化结构：
- search.py：关键词搜索采集
- channel.py：频道列表采集（中央/地方/分省）
- detail.py：详情页解析
- parser.py：列表项解析
- regions.py：31 省 zoneId 注册表
- utils.py：ccgp 专用工具
"""
import logging
import re

from scraper.base import BaseScraper
from scraper.keywords import CCGP_KEYWORDS_FINAL
from scraper.ccgp.regions import REGIONS
from scraper.ccgp.search import scrape_search_page
from scraper.ccgp.channel import scrape_channel_page
from scraper.ccgp.detail import fetch_detail

logger = logging.getLogger(__name__)

# "中央公告/地方公告"频道页支持的频道标识
# 采集配置里用 'channel:zygg' / 'channel:dfgg' / 'channel:dfgg:guangdong' 伪关键词
_CHANNEL_KEYWORD_RE = re.compile(r'^channel:(zygg|dfgg)(?::(\w+))?$')


class CcgpScraper(BaseScraper):
    """中国政府采购网爬虫。

    搜索 URL: http://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index={page}&kw={keyword}

    支持三种采集模式：
    1. 关键词搜索：直接传文本关键词（如 "管道"、"给排水工程"）
    2. 频道采集：伪关键词 "channel:zygg"（中央公告）、"channel:dfgg"（地方公告混合）
    3. 分省频道：伪关键词 "channel:dfgg:guangdong"（广东省地方公告）
    """

    source_type = 'ccgp'
    base_url = 'http://search.ccgp.gov.cn/bxsearch'
    referer = 'http://www.ccgp.gov.cn/'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.ccgp_keywords = list(CCGP_KEYWORDS_FINAL)

    def default_keywords(self):
        """生成默认关键词列表：关键词搜索词 + 频道伪关键词。

        频道清单：1 个中央公告 + 31 个省的地方公告 = 32 个频道
        + ~40 个去重后的搜索关键词 ≈ 72 个采集单元
        """
        keywords = list(self.ccgp_keywords)
        keywords.append('channel:zygg')  # 中央公告频道
        # 31 个省级行政区的地方公告频道
        for region_code in REGIONS:
            keywords.append(f'channel:dfgg:{region_code}')
        return keywords

    def _keyword_display(self, keyword):
        """将伪关键词转换为用户友好名称用于进度展示。"""
        m = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if m:
            channel = m.group(1)
            region_code = m.group(2)
            channel_name = '中央公告' if channel == 'zygg' else '地方公告'
            if region_code:
                region = REGIONS.get(region_code)
                region_name = region['name'] if region else region_code
                return f'{channel_name}·{region_name}'
            return f'{channel_name}（全国）'
        return keyword

    def _scrape_page(self, keyword, page):
        """采集单页。根据关键词类型分发到搜索或频道采集。"""
        channel_match = _CHANNEL_KEYWORD_RE.match(keyword or '')
        if channel_match:
            channel = channel_match.group(1)
            region_code = channel_match.group(2) or None
            return scrape_channel_page(self, channel, page, region_code=region_code)

        # 普通关键词 → 搜索采集
        return scrape_search_page(self, keyword, page)

    def _fetch_detail(self, url):
        """获取详情页并解析补充信息（迁移至 detail.py，保留实例方法兼容）。"""
        return fetch_detail(self, url)

    def run(self, keywords=None, max_pages=None):
        """执行采集。

        关键词搜索默认 max_pages=5，频道采集默认 max_pages=2。
        分省采集的单省公告量有限，无需翻太多页。
        """
        if keywords is None:
            keywords = self.default_keywords()

        # 按关键词类型分配不同的 max_pages
        if max_pages is None:
            results = []
            for kw in keywords:
                kw_max_pages = 2 if kw.startswith('channel:') else 5
                results.append(super().run(keywords=[kw], max_pages=kw_max_pages))
            return sum(results)
        # 手动指定 keywords 时，统一使用传入的 max_pages
        return super().run(keywords=keywords, max_pages=max_pages)
