# -*- coding: utf-8 -*-
"""江苏省公共资源交易平台爬虫 (jsggzy.jszwfw.gov.cn)。

基于 EpointWebBuilder 通用模块（scraper.epoint），仅需定义江苏省特定配置。
"""
import logging

from scraper.epoint import EpointBaseScraper
from scraper.ggzyjy_js.regions import REGIONS

logger = logging.getLogger(__name__)


class JsGgzyjyScraper(EpointBaseScraper):
    """江苏省公共资源交易平台爬虫。

    API 地址: http://jsggzy.jszwfw.gov.cn/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew (POST)

    使用 EpointWebBuilder CMS 的 Elasticsearch 搜索 API，
    与浙江/四川共享通用解析逻辑（scraper.epoint 模块）。

    与浙江的关键差异：
    - CATEGORY_NUM = '003001001'（建设工程招标，前缀 003 而非 002）
    - TIME_FIELD = 'infodatepx'（而非 webdate）
    - base_url 使用 HTTP（HTTPS 证书无效）
    """

    source_type = 'ggzyjy_js'
    base_url = 'http://jsggzy.jszwfw.gov.cn'
    referer = 'http://jsggzy.jszwfw.gov.cn/'
    REGIONS = REGIONS
    CATEGORY_NUM = '003001001'  # 建设工程 - 招标公告
    TIME_FIELD = 'infodatepx'
