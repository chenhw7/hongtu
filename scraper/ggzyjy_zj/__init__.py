# -*- coding: utf-8 -*-
"""浙江省公共资源交易平台爬虫 (ggzy.zj.gov.cn)。

基于 EpointWebBuilder 通用模块（scraper.epoint），仅需定义浙江省特定配置。
"""
import logging

from scraper.epoint import EpointBaseScraper
from scraper.ggzyjy_zj.regions import REGIONS

logger = logging.getLogger(__name__)


class ZjGgzyjyScraper(EpointBaseScraper):
    """浙江省公共资源交易平台爬虫。

    API 地址: https://ggzy.zj.gov.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew (POST)

    使用 EpointWebBuilder CMS 的 Elasticsearch 搜索 API，
    与四川/江苏共享通用解析逻辑（scraper.epoint 模块）。
    """

    source_type = 'ggzyjy_zj'
    base_url = 'https://ggzy.zj.gov.cn'
    referer = 'https://ggzy.zj.gov.cn/'
    REGIONS = REGIONS
    CATEGORY_NUM = '002001001'  # 工程建设 - 招标公告
    TIME_FIELD = 'webdate'
