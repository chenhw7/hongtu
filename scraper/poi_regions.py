# -*- coding: utf-8 -*-
"""POI 采集地区配置（全国重点城市）。

按省份分组，支持分批采集以控制高德 API 配额消耗。
选择标准：省会城市 + 经济发达地级市 + 管道需求密集城市。
"""

# ------------------------------------------------------------------
# 广东省（现有，保持不变）
# ------------------------------------------------------------------
GUANGDONG_CITIES = [
    '广州', '深圳', '珠海', '汕头', '佛山', '韶关', '河源', '梅州', '惠州',
    '汕尾', '东莞', '中山', '江门', '阳江', '湛江', '茂名', '肇庆', '清远',
    '潮州', '揭阳', '云浮',
]

# ------------------------------------------------------------------
# 全国其他重点城市（按省份分组，直辖市单独成组）
# ------------------------------------------------------------------
NATIONAL_CITIES = {
    '广西': ['南宁', '柳州', '桂林', '北海', '玉林'],
    '福建': ['福州', '厦门', '泉州', '漳州', '莆田'],
    '湖南': ['长沙', '株洲', '湘潭', '衡阳', '岳阳'],
    '江西': ['南昌', '九江', '赣州', '景德镇'],
    '海南': ['海口', '三亚'],
    '浙江': ['杭州', '宁波', '温州', '绍兴', '嘉兴', '金华'],
    '江苏': ['南京', '苏州', '无锡', '常州', '南通', '徐州'],
    '上海': ['上海'],
    '北京': ['北京'],
    '天津': ['天津'],
    '重庆': ['重庆'],
    '山东': ['济南', '青岛', '烟台', '潍坊', '临沂'],
    '河北': ['石家庄', '唐山', '保定', '廊坊'],
    '河南': ['郑州', '洛阳', '开封', '南阳'],
    '湖北': ['武汉', '宜昌', '襄阳'],
    '四川': ['成都', '绵阳', '德阳'],
    '安徽': ['合肥', '芜湖', '蚌埠'],
    '辽宁': ['沈阳', '大连'],
    '吉林': ['长春'],
    '黑龙江': ['哈尔滨'],
    '陕西': ['西安', '咸阳'],
    '山西': ['太原'],
    '云南': ['昆明'],
    '贵州': ['贵阳'],
    '甘肃': ['兰州'],
    '内蒙古': ['呼和浩特', '包头'],
    '新疆': ['乌鲁木齐'],
    '宁夏': ['银川'],
    '青海': ['西宁'],
    '西藏': ['拉萨'],
}


def get_all_cities():
    """获取全部城市列表（广东 + 全国）。"""
    all_cities = list(GUANGDONG_CITIES)
    for province_cities in NATIONAL_CITIES.values():
        all_cities.extend(province_cities)
    return all_cities


def get_cities_by_province(province):
    """获取指定省份的城市列表。

    province: 省份名称（如 '广东'、'浙江'），'广东' 返回 GUANGDONG_CITIES。
    """
    if province == '广东':
        return list(GUANGDONG_CITIES)
    return list(NATIONAL_CITIES.get(province, []))


def get_guangdong_cities():
    """获取广东省城市列表。"""
    return list(GUANGDONG_CITIES)


def get_national_cities():
    """获取全国重点城市列表（不含广东）。"""
    all_cities = []
    for province_cities in NATIONAL_CITIES.values():
        all_cities.extend(province_cities)
    return all_cities


def get_batch_cities(batch_index, batch_size=3):
    """按批次获取城市列表（用于分批采集控制配额）。

    将全国省份（含广东作为一个整体）按 batch_size 分组，返回第 batch_index 批
    的城市列表。batch_index 从 0 开始，超出范围返回空列表。

    batch_index: 从 0 开始的批次号
    batch_size: 每批包含的省份数（默认 3）
    """
    # 构建省份顺序列表，广东排第一
    province_order = ['广东'] + list(NATIONAL_CITIES.keys())
    # 按 batch_size 切片
    start = batch_index * batch_size
    end = start + batch_size
    if start >= len(province_order):
        return []
    batch_provinces = province_order[start:end]
    cities = []
    for province in batch_provinces:
        cities.extend(get_cities_by_province(province))
    return cities


def get_city_count():
    """获取城市总数（广东 + 全国）。"""
    national_count = sum(len(v) for v in NATIONAL_CITIES.values())
    return len(GUANGDONG_CITIES) + national_count


def get_province_count():
    """获取省份总数（含广东）。"""
    return 1 + len(NATIONAL_CITIES)


def get_batch_count(batch_size=3):
    """获取按指定 batch_size 分批时的总批次数。"""
    province_count = get_province_count()
    return (province_count + batch_size - 1) // batch_size
