# -*- coding: utf-8 -*-
"""省级/市级生态环境部门建设项目环评公示采集。

公示中的联系人和电话属于生态环境主管部门，不是建设单位联系人，仅供项目真实性
核验。广州受理附件受图形验证码和每 IP 下载次数限制；东莞附件要求表单 POST，首期
均只保存源附件元数据，不交给 BaseScraper 的 GET 附件下载流程。
"""
import logging

from scraper.base import BaseScraper
from scraper.eia.regions import REGIONS
from scraper.eia.adapters import get_adapter

logger = logging.getLogger(__name__)


class EiaScraper(BaseScraper):
    """环评公示采集器。

    根据 REGIONS 中每个城市的 adapter 配置，自动分发到对应的采集适配器：
    - 无 adapter：静态 HTML 适配器（覆盖约 15 个城市）
    - guangzhou：广州 JSON API + 静态 HTML
    - dongguan：东莞 POST 表单 API
    - shenzhen：深圳 .vm 服务端渲染
    - zhaoqing：肇庆 gkmlpt JSON API
    """
    source_type = 'eia'
    base_url = 'https://gdee.gd.gov.cn/jsxmsp3189/'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.dongguan_lookback_days = 2
        self.zhaoqing_lookback_days = 3
        self.anti_scrape_wait = 0
        # 适配器实例缓存（懒加载）
        self._adapters = {}
        if app is not None:
            self.delay_min = app.config.get('EIA_DELAY_MIN', self.delay_min)
            self.delay_max = app.config.get('EIA_DELAY_MAX', self.delay_max)
            self.anti_scrape_wait = app.config.get('EIA_ANTI_SCRAPE_WAIT', 0)
            self.dongguan_lookback_days = max(
                1, int(app.config.get('EIA_DONGGUAN_LOOKBACK_DAYS', self.dongguan_lookback_days))
            )
            self.zhaoqing_lookback_days = max(
                1, int(app.config.get('EIA_ZHAOQING_LOOKBACK_DAYS', self.zhaoqing_lookback_days))
            )

    # ------------------------------------------------------------------
    # BaseScraper 接口
    # ------------------------------------------------------------------
    def default_keywords(self):
        """生成默认的 "region:地区代码" 伪关键词，覆盖所有已配置数据源。"""
        return [f'region:{key}' for key in REGIONS]

    def _keyword_display(self, keyword):
        """将 region:xxx 伪关键词转换为地区名称用于进度展示。"""
        if keyword.startswith('region:'):
            region_key = keyword.split(':', 1)[1]
            region = REGIONS.get(region_key)
            return region['name'] if region else keyword
        return keyword

    def run(self, keywords=None, max_pages=5):
        if not keywords:
            keywords = self.default_keywords()
        return super().run(keywords=keywords, max_pages=max_pages)

    def _scrape_page(self, keyword, page):
        """按关键词分发到对应地区的适配器。"""
        region_key = keyword.split(':', 1)[1] if keyword.startswith('region:') else None
        region = REGIONS.get(region_key)
        if region is None:
            logger.error('[eia] 无效的地区代码: %s', keyword)
            return None

        adapter = self._get_adapter(region)
        return adapter.scrape_page(region, page)

    def _get_adapter(self, region):
        """获取或创建地区对应的适配器实例（懒加载 + 缓存）。"""
        adapter_key = region.get('adapter') or '_static'
        if adapter_key not in self._adapters:
            self._adapters[adapter_key] = get_adapter(region, self)
        return self._adapters[adapter_key]