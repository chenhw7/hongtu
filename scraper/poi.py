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
            self.poi_cities = app.config.get('POI_CITIES', [])
        else:
            self.amap_key = ''
            self.poi_keywords = []
            self.poi_cities = []

    def default_keywords(self):
        """生成默认的 "关键词@城市" 伪关键词组合（配置的关键词 x 广东地级市）"""
        return [f'{kw}@{city}' for kw in self.poi_keywords for city in self.poi_cities]

    def run(self, keywords=None, max_pages=3):
        if not self.amap_key:
            logger.error('[poi] 未配置 AMAP_API_KEY，无法采集')
            task = self.create_task(self.source_type, self.base_url)
            self.update_task(
                task.id, '失败', result_count=0,
                error_msg='未配置 AMAP_API_KEY，请到 https://lbs.amap.com/ 申请个人开发者Key'
                          '（服务平台选"Web服务"），并通过环境变量 AMAP_API_KEY 注入后重试',
            )
            return 0
        if not keywords:
            keywords = self.default_keywords()
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
