# -*- coding: utf-8 -*-
"""地图POI采集：通过高德地图 Web服务API 关键词搜索，采集管道经销商/门店/工厂

作为潜在客户（经销渠道）落库到 Customer 表，与政府采购类线索（Lead 表）区分开。

高德地图 Web服务API "关键字搜索"（v3/place/text）是完全公开合规的官方接口，
不涉及爬取地图网页本身，需要在 https://lbs.amap.com/ 申请个人开发者Key
（应用服务平台选"Web服务"，不是"Web端(JS API)"），通过环境变量 AMAP_API_KEY
注入，不写入代码仓库。

复用 BaseScraper 的任务记录/实时进度/暂停继续停止机制：把"关键词+城市"编码为
伪关键词 "关键词@城市"（与 gdgpo.py 里 "channel:xxx" 伪关键词是同一种技巧），
交给 BaseScraper.run() 的 keyword×page 循环驱动，只需重写 _scrape_page() 和
save_leads()（改为写 Customer 表而不是 Lead 表），不需要重复实现主流程。
"""
import logging

from scraper import poi_regions
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class AmapPoiScraper(BaseScraper):
    source_type = 'poi'
    base_url = 'https://restapi.amap.com/v3/place/text'

    def __init__(self, app=None):
        super().__init__(app)
        if app is not None:
            self.amap_key = app.config.get('AMAP_API_KEY', '')
            self.poi_keywords = app.config.get('POI_KEYWORDS', [])
            # 兼容旧配置：优先使用 app.config['POI_CITIES']，
            # 若 POI_SCOPE='national' 则使用全国城市
            self.poi_scope = app.config.get('POI_SCOPE', 'guangdong')
            self.poi_cities = self._resolve_cities(app)
        else:
            self.amap_key = ''
            self.poi_keywords = []
            self.poi_scope = 'guangdong'
            self.poi_cities = poi_regions.get_guangdong_cities()

    def _resolve_cities(self, app):
        """根据 POI_SCOPE 决定城市列表。

        - 'guangdong'：使用 poi_regions.get_guangdong_cities()（默认，向后兼容）
        - 'national'：使用 poi_regions.get_all_cities()（全部城市）
        - 若 config 中仍有显式 POI_CITIES（非默认广东省列表），优先使用之
        """
        config_cities = app.config.get('POI_CITIES', [])
        scope = self.poi_scope

        if scope == 'national':
            logger.info('[poi] POI_SCOPE=national，使用全国重点城市列表')
            return poi_regions.get_all_cities()
        # 默认 guangdong
        if config_cities and config_cities != poi_regions.GUANGDONG_CITIES:
            # 用户显式配置了非默认城市列表，尊重之
            logger.info('[poi] 使用 app.config[POI_CITIES]（自定义配置，%d 个城市）',
                        len(config_cities))
            return list(config_cities)
        logger.info('[poi] POI_SCOPE=guangdong，使用广东省 21 城')
        return poi_regions.get_guangdong_cities()

    def default_keywords(self, cities=None):
        """生成默认的 "关键词@城市" 伪关键词组合（配置的关键词 x 指定城市列表）"""
        city_list = cities if cities is not None else self.poi_cities
        return [f'{kw}@{city}' for kw in self.poi_keywords for city in city_list]

    def run(self, keywords=None, max_pages=3, cities=None, batch=None):
        """执行 POI 采集。

        Args:
            keywords: 自定义伪关键词列表（"关键词@城市"），None 则自动生成。
            max_pages: 每关键词最大采集页数。
            cities: 指定城市列表，None 则使用 self.poi_cities。
            batch: 批次号（从 0 开始），指定后自动从 poi_regions 获取该批城市，
                   覆盖 cities 参数。用于分批采集控制高德 API 配额消耗。
        """
        if not self.amap_key:
            logger.error('[poi] 未配置 AMAP_API_KEY，无法采集')
            task = self.create_task(self.source_type, self.base_url)
            self.update_task(
                task.id, '失败', result_count=0,
                error_msg='未配置 AMAP_API_KEY，请到 https://lbs.amap.com/ 申请个人开发者Key'
                          '（服务平台选"Web服务"），并通过环境变量 AMAP_API_KEY 注入后重试',
            )
            return 0

        # 批次优先：batch 参数覆盖 cities
        if batch is not None:
            cities = poi_regions.get_batch_cities(batch)
            if not cities:
                logger.warning('[poi] batch=%d 超出范围，无城市可采集', batch)
                return 0
            logger.info('[poi] 批次 %d，采集 %d 个城市: %s',
                        batch, len(cities), '、'.join(cities[:5]) + ('...' if len(cities) > 5 else ''))

        if not keywords:
            keywords = self.default_keywords(cities=cities)
        return super().run(keywords=keywords, max_pages=max_pages)

    def _scrape_page(self, keyword, page):
        """采集单页POI搜索结果

        keyword 格式为 "关键词@城市"（默认组合）或纯关键词（用户手动输入，
        不限城市，citylimit=false 全国范围搜索）。

        Returns:
            list[dict] 或 None（请求失败/接口报错）
        """
        if '@' in keyword:
            kw, city = keyword.split('@', 1)
        else:
            kw, city = keyword, ''

        params = {
            'key': self.amap_key,
            'keywords': kw,
            'city': city,
            'citylimit': 'true' if city else 'false',
            'offset': 25,
            'page': page,
            'extensions': 'base',
        }
        response = self.fetch(self.base_url, params=params, extra_headers={'Accept': 'application/json'})
        if response is None:
            return None

        try:
            data = response.json()
        except Exception:
            logger.warning('[poi] 响应不是合法JSON: %s', response.text[:200])
            return None

        if data.get('status') != '1':
            logger.warning('[poi] 高德接口返回错误: %s', data.get('info'))
            return None

        pois = data.get('pois') or []
        return [self._poi_to_item(poi, kw, city) for poi in pois]

    @staticmethod
    def _poi_to_item(poi, keyword, city):
        name = (poi.get('name') or '').strip()
        address = ''.join(p for p in (
            poi.get('pname', ''), poi.get('cityname', ''), poi.get('adname', ''), poi.get('address', ''),
        ) if p)
        tel = (poi.get('tel') or '').split(';')[0].strip()
        return {
            'company_name': name,
            'phone': tel,
            'address': address,
            'notes': '高德地图POI采集｜关键词:%s｜城市:%s｜类目:%s(%s)｜坐标:%s' % (
                keyword, city or '不限', poi.get('type', ''), poi.get('typecode', ''), poi.get('location', ''),
            ),
        }

    def save_leads(self, leads_data, source_type):
        """保存POI结果到 Customer 表（潜在客户/经销渠道），按 公司名+地址 去重"""
        from app.models import Customer
        from app.extensions import db

        new_count = 0
        for item in leads_data:
            name = (item.get('company_name') or '').strip()
            if not name:
                continue
            address = item.get('address', '')

            existing = Customer.query.filter_by(company_name=name, address=address).first()
            if existing:
                continue

            customer = Customer(
                company_name=name,
                phone=item.get('phone', ''),
                address=address,
                industry_type='经销商/建材',
                source='地图POI采集',
                status='新线索',
                notes=item.get('notes', ''),
            )
            db.session.add(customer)
            try:
                db.session.commit()
                new_count += 1
            except Exception:
                db.session.rollback()
                logger.warning('[poi] 保存客户失败（可能重复）: %s', name)
                continue

        return new_count
