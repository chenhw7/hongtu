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

    2026-07 实测发现：浙江站 ES API 已升级为 keyword/pageNo/pageSize 格式，
    不再接受 wd/pn/rn/cnum 格式（后者返回 total=0）。
    因此覆盖 _scrape_page 使用新格式请求，复用 epoint 的 _process_page 解析。
    """

    source_type = 'ggzyjy_zj'
    base_url = 'https://ggzy.zj.gov.cn'
    referer = 'https://ggzy.zj.gov.cn/'
    REGIONS = REGIONS
    CATEGORY_NUM = '002001001'  # 工程建设 - 招标公告
    TIME_FIELD = 'webdate'

    # 浙江 ES API 使用 keyword/pageNo 格式（而非 wd/pn 格式）
    _API_PATH = '/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew'

    def _scrape_page(self, keyword, page):
        """浙江站 ES API 搜索（keyword/pageNo 格式）。"""
        from scraper.epoint.search import _post_search, _process_page

        body = {
            'keyword': keyword or '',
            'pageNo': page,
            'pageSize': self.PAGE_SIZE,
        }
        api_url = self.base_url.rstrip('/') + self._API_PATH
        payload = _post_search(self, body, api_url_override=api_url)
        return _process_page(self, payload)
