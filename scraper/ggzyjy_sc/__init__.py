# -*- coding: utf-8 -*-
"""四川省公共资源交易平台爬虫 (ggzyjy.sc.gov.cn)。

基于 EpointWebBuilder 通用模块（scraper.epoint），仅需定义四川省特定配置。
"""
import logging

from scraper.epoint import EpointBaseScraper
from scraper.ggzyjy_sc.regions import REGIONS

logger = logging.getLogger(__name__)


class ScGgzyjyScraper(EpointBaseScraper):
    """四川省公共资源交易平台爬虫。

    API 地址: https://ggzyjy.sc.gov.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew (POST)

    使用 EpointWebBuilder CMS 的 Elasticsearch 搜索 API，
    与浙江/江苏共享通用解析逻辑（scraper.epoint 模块）。
    """

    source_type = 'ggzyjy_sc'
    base_url = 'https://ggzyjy.sc.gov.cn'
    REGIONS = REGIONS
    CATEGORY_NUM = '002001001'  # 工程建设 - 招标公告
    TIME_FIELD = 'webdate'

    # 四川使用多个候选 Referer，每次请求随机选取，降低指纹特征
    REFERERS = [
        'https://ggzyjy.sc.gov.cn/',
        'https://ggzyjy.sc.gov.cn/jyxx/002001/002001001',
        'https://ggzyjy.sc.gov.cn/jyxx/002001',
        'https://ggzyjy.sc.gov.cn/jyxx',
        'https://www.google.com/',
    ]
