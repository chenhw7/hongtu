# -*- coding: utf-8 -*-
"""广东省政府采购信息爬虫

通过中国政府采购网(ccgp)的区域筛选功能采集广东省采购信息。
原 gdgpo.czt.gd.gov.cn 已迁移为 JS 渲染的 SPA(freecms)，
httpx 无法直接抓取，改用 ccgp 的 zoneId 参数筛选广东数据。
"""
from scraper.ccgp import CcgpScraper


class GdgpoScraper(CcgpScraper):
    """广东省采购信息爬虫（基于 ccgp 广东区域筛选）"""

    source_type = 'gdgpo'

    def _build_search_url(self, keyword, page):
        url, params = super()._build_search_url(keyword, page)
        params['displayZone'] = '广东'
        params['zoneId'] = '44'
        return url, params
