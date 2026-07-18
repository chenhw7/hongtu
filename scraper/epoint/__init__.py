# -*- coding: utf-8 -*-
"""EpointWebBuilder CMS 平台通用爬虫中间基类。

供浙江/四川/江苏等使用 EpointWebBuilder + Elasticsearch 搜索 API 的
公共资源交易平台复用。子类仅需定义少量类属性即可接入。

模块结构：
- search.py：getFullTextDataNew ES API 通用调用封装
- parser.py：ES API JSON 响应 → Lead dict 通用解析
- detail.py：SSR HTML 详情页解析（BeautifulSoup）
- utils.py：日期/金额/HTML 清洗工具
"""
import logging
import random

from scraper.base import BaseScraper
from scraper.keywords import GGZYJY_KEYWORDS_FINAL
from scraper.epoint.search import search_page

logger = logging.getLogger(__name__)


class EpointBaseScraper(BaseScraper):
    """EpointWebBuilder 平台通用爬虫基类。

    子类仅需定义：
    - source_type:   数据源标识（如 'ggzyjy_zj'）
    - base_url:      站点根 URL（如 'https://ggzy.zj.gov.cn'）
    - referer:       Referer 头（字符串，或 REFERERS 列表随机选取）
    - REFERERS:      Referer 候选列表（优先于 referer 字符串）
    - REGIONS:       地区码字典 {code: {'name': 'xxx', ...}}
    - CATEGORY_NUM:  分类编码（如 "002001001" = 招标公告）
    - TIME_FIELD:    时间字段名（"webdate" 或 "infodatepx"）
    """

    REGIONS = {}
    CATEGORY_NUM = '002001001'
    TIME_FIELD = 'webdate'
    PAGE_SIZE = 20
    REFERERS = []  # 子类可定义 Referer 候选列表

    def __init__(self, app=None):
        super().__init__(app=app)
        self.keywords = list(GGZYJY_KEYWORDS_FINAL)

    def get_random_referer(self):
        """从 REFERERS 列表随机选一个 Referer，未配置时返回类属性 referer。"""
        if self.REFERERS:
            return random.choice(self.REFERERS)
        return self.referer

    def _scrape_page(self, keyword, page):
        """采集单页搜索结果，委托给 search.py 的通用实现。"""
        return search_page(self, keyword, page)
