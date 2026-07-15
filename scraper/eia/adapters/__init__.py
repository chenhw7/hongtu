# -*- coding: utf-8 -*-
"""环评公示适配器注册表。

通过 region['adapter'] 字段查找对应的适配器类，无 adapter 字段默认使用 StaticAdapter。
"""
from scraper.eia.adapters.static import StaticAdapter
from scraper.eia.adapters.guangzhou import GuangzhouAdapter
from scraper.eia.adapters.dongguan import DongguanAdapter
from scraper.eia.adapters.shenzhen import ShenzhenAdapter
from scraper.eia.adapters.zhaoqing import ZhaoqingAdapter

ADAPTERS = {
    'guangzhou': GuangzhouAdapter,
    'dongguan': DongguanAdapter,
    'shenzhen': ShenzhenAdapter,
    'zhaoqing': ZhaoqingAdapter,
}


def get_adapter(region, scraper):
    """根据 region 配置创建对应的适配器实例。"""
    adapter_name = region.get('adapter')
    adapter_cls = ADAPTERS.get(adapter_name, StaticAdapter)
    return adapter_cls(scraper)