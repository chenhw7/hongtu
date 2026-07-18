# -*- coding: utf-8 -*-
"""广州市住建局爬虫 (zfcj.gz.gov.cn)。

采集两类数据：
- 施工许可证公示（jzgdsgxkxxlb）
- 竣工验收备案（gcjgysxxlb）

模块结构：
- api.py：AJAX API 调用封装（POST + query string）
- parser.py：API 响应 → Lead dict 字段映射
"""
import logging

from scraper.base import BaseScraper
from scraper.keywords import PLATFORM_KEYWORDS_FINAL
from scraper.gzfcj.api import fetch_permit_page, fetch_acceptance_page
from scraper.gzfcj.parser import parse_permit_item, parse_acceptance_item

logger = logging.getLogger(__name__)


class GzfcjScraper(BaseScraper):
    """广州市住建局爬虫。

    采集施工许可证公示和竣工验收备案信息，通过 AJAX JSON API 获取数据。

    API 端点：
    - 施工许可证: POST /ysqgk/Api/WebApi/jzgdsgxkxxlb.ashx
    - 竣工验收:   POST /ysqgk/Api/WebApi/gcjgysxxlb.ashx
    """

    source_type = 'gzfcj'
    base_url = 'https://zfcj.gz.gov.cn'
    referer = 'https://zfcj.gz.gov.cn/zfcj/gczlaq/constructionPermitInformation'

    def __init__(self, app=None):
        super().__init__(app=app)
        # 复用平台类关键词（管道产品 + 工程类型 + 材料品类 + 项目类型）
        self.gzfcj_keywords = list(PLATFORM_KEYWORDS_FINAL)

    def default_keywords(self):
        """生成默认关键词列表。"""
        return list(self.gzfcj_keywords)

    def _scrape_page(self, keyword, page):
        """采集单页：先采集施工许可证，再采集竣工验收备案，合并返回。

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            list[dict] or None: 线索列表，None 表示请求失败
        """
        leads = []

        # 1. 采集施工许可证公示
        permit_payload = fetch_permit_page(self, keyword=keyword, page=page)
        if permit_payload is None:
            # 施工许可证接口失败，记录但不中断（继续采集竣工验收）
            logger.warning('[gzfcj] 施工许可证接口失败，关键词="%s" 第%d页', keyword, page)
        else:
            permit_data = permit_payload.get('data') or []
            if not permit_data:
                logger.info('[gzfcj] 施工许可证无结果: 关键词="%s" 第%d页', keyword, page)
            else:
                for item in permit_data:
                    lead = parse_permit_item(item)
                    if lead.get('project_name'):
                        leads.append(lead)

        # 2. 采集竣工验收备案
        acceptance_payload = fetch_acceptance_page(self, keyword=keyword, page=page)
        if acceptance_payload is None:
            logger.warning('[gzfcj] 竣工验收接口失败，关键词="%s" 第%d页', keyword, page)
        else:
            acceptance_data = acceptance_payload.get('data') or []
            if not acceptance_data:
                logger.info('[gzfcj] 竣工验收无结果: 关键词="%s" 第%d页', keyword, page)
            else:
                for item in acceptance_data:
                    lead = parse_acceptance_item(item)
                    if lead.get('project_name'):
                        leads.append(lead)

        # 两个接口都失败时返回 None（触发基类的失败逻辑）
        if permit_payload is None and acceptance_payload is None:
            return None

        return leads
