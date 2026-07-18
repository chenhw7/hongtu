# -*- coding: utf-8 -*-
"""数据源注册表（Source Registry）。

集中管理所有采集器的元信息，消除分散在路由/调度/模板中的逐源硬编码。
新增数据源仅需在此文件追加一条记录。
"""
import importlib
import logging

logger = logging.getLogger(__name__)

SCRAPER_REGISTRY = {
    'ccgp': {
        'label': '中国政府采购网',
        'import_path': 'scraper.ccgp',
        'class_name': 'CcgpScraper',
        'badge_class': 'badge-accent',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'http://www.ccgp.gov.cn/',
    },
    'gdgpo': {
        'label': '广东省政府采购网',
        'import_path': 'scraper.gdgpo',
        'class_name': 'GdgpoScraper',
        'badge_class': 'badge-green',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://gdgpo.czt.gd.gov.cn/',
    },
    'eia': {
        'label': '环评公示',
        'import_path': 'scraper.eia',
        'class_name': 'EiaScraper',
        'badge_class': 'badge-accent',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': '',
    },
    'ggzyjy': {
        'label': '公共资源交易',
        'import_path': 'scraper.ggzyjy',
        'class_name': 'GgzyjyScraper',
        'badge_class': 'badge-teal',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://ygp.gdzwfw.gov.cn/',
    },
    'poi': {
        'label': '高德地图POI',
        'import_path': 'scraper.poi',
        'class_name': 'AmapPoiScraper',
        'badge_class': 'badge-amber',
        'include_in_all': False,  # POI 产出 Customer 而非 Lead
        'is_lead_source': False,
        'source_site': 'https://lbs.amap.com/',
    },
    'fdtz': {
        'label': '发改委项目审批',
        'import_path': 'scraper.fdtz',
        'class_name': 'FdtzScraper',
        'badge_class': 'badge-purple',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://tzxm.gd.gov.cn/',
    },
    'pipebiz': {
        'label': '管道商务网',
        'import_path': 'scraper.pipebiz',
        'class_name': 'PipebizScraper',
        'badge_class': 'badge-indigo',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://www.chinapipe.net/',
    },
    'ggzyjy_zj': {
        'label': '浙江公共资源交易',
        'import_path': 'scraper.ggzyjy_zj',
        'class_name': 'ZjGgzyjyScraper',
        'badge_class': 'badge-teal',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://ggzy.zj.gov.cn/',
    },
    'gzfcj': {
        'label': '广州住建局',
        'import_path': 'scraper.gzfcj',
        'class_name': 'GzfcjScraper',
        'badge_class': 'badge-cyan',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://zfcj.gz.gov.cn/',
    },
    'bjx': {
        'label': '北极星环保网',
        'import_path': 'scraper.bjx',
        'class_name': 'BjxScraper',
        'badge_class': 'badge-green',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://huanbao.bjx.com.cn/',
    },
    'gdcic': {
        'label': '广东住建厅',
        'import_path': 'scraper.gdcic',
        'class_name': 'GdcicScraper',
        'badge_class': 'badge-indigo',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://www.gdcic.net/',
    },
    'ggzyjy_sc': {
        'label': '四川公共资源交易',
        'import_path': 'scraper.ggzyjy_sc',
        'class_name': 'ScGgzyjyScraper',
        'badge_class': 'badge-teal',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'https://ggzyjy.sc.gov.cn/',
    },
    'ggzyjy_js': {
        'label': '江苏公共资源交易',
        'import_path': 'scraper.ggzyjy_js',
        'class_name': 'JsGgzyjyScraper',
        'badge_class': 'badge-teal',
        'include_in_all': True,
        'is_lead_source': True,
        'source_site': 'http://jsggzy.jszwfw.gov.cn/',
    },
    'qcc': {
        'label': '企查查',
        'import_path': 'scraper.qcc',
        'class_name': 'QccScraper',
        'badge_class': 'badge-purple',
        'include_in_all': False,  # 付费 API，不参与全量采集
        'is_lead_source': False,  # 产出企业画像而非招标线索
        'source_site': 'https://openapi.qcc.com/',
    },
}


def get_scraper_class(source_type):
    """动态加载采集器类。

    Args:
        source_type: 数据源标识（如 'ccgp', 'gdgpo'）

    Returns:
        采集器类，未找到返回 None
    """
    entry = SCRAPER_REGISTRY.get(source_type)
    if not entry:
        return None
    try:
        module = importlib.import_module(entry['import_path'])
        return getattr(module, entry['class_name'])
    except (ImportError, AttributeError) as e:
        logger.error('加载采集器 %s 失败: %s', source_type, e)
        return None


def get_all_source_types(include_in_all=False, lead_only=False):
    """获取数据源标识列表。

    Args:
        include_in_all: 仅返回参与"全部采集"的数据源
        lead_only: 仅返回产出 Lead 的数据源
    """
    result = []
    for key, entry in SCRAPER_REGISTRY.items():
        if include_in_all and not entry.get('include_in_all'):
            continue
        if lead_only and not entry.get('is_lead_source'):
            continue
        result.append(key)
    return result


def get_source_label(source_type):
    """获取数据源中文标签，未注册时返回原始标识。"""
    entry = SCRAPER_REGISTRY.get(source_type)
    return entry['label'] if entry else source_type


def get_source_badge_class(source_type):
    """获取数据源的 badge CSS 类名。"""
    entry = SCRAPER_REGISTRY.get(source_type)
    return entry.get('badge_class', 'badge-slate') if entry else 'badge-slate'


def get_source_choices():
    """生成表单下拉选项列表 [(value, label), ...]。"""
    choices = [(key, entry['label']) for key, entry in SCRAPER_REGISTRY.items()
               if entry.get('is_lead_source')]
    choices.append(('手动录入', '手动录入'))
    return choices


def get_source_sites():
    """生成官网地址字典 {source_type: url}。"""
    return {key: entry['source_site'] for key, entry in SCRAPER_REGISTRY.items()
            if entry.get('source_site')}
