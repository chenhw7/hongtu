# -*- coding: utf-8 -*-
"""ccgp 省级行政区注册表（zoneId 映射，31 个省级行政区）。

zoneId 采用 GB/T 2260 行政区划代码前两位 + "0000" 格式。
⚠️ 来源需实际验证：ccgp 搜索接口的 zoneId 参数不一定是国标行政区划代码，
   如果实际抓包发现不一致，需更新此表。
"""

REGIONS = {
    'beijing':    {'name': '北京市', 'zoneId': '110000'},
    'tianjin':    {'name': '天津市', 'zoneId': '120000'},
    'hebei':      {'name': '河北省', 'zoneId': '130000'},
    'shanxi':     {'name': '山西省', 'zoneId': '140000'},
    'neimenggu':  {'name': '内蒙古自治区', 'zoneId': '150000'},
    'liaoning':   {'name': '辽宁省', 'zoneId': '210000'},
    'jilin':      {'name': '吉林省', 'zoneId': '220000'},
    'heilongjiang': {'name': '黑龙江省', 'zoneId': '230000'},
    'shanghai':   {'name': '上海市', 'zoneId': '310000'},
    'jiangsu':    {'name': '江苏省', 'zoneId': '320000'},
    'zhejiang':   {'name': '浙江省', 'zoneId': '330000'},
    'anhui':      {'name': '安徽省', 'zoneId': '340000'},
    'fujian':     {'name': '福建省', 'zoneId': '350000'},
    'jiangxi':    {'name': '江西省', 'zoneId': '360000'},
    'shandong':   {'name': '山东省', 'zoneId': '370000'},
    'henan':      {'name': '河南省', 'zoneId': '410000'},
    'hubei':      {'name': '湖北省', 'zoneId': '420000'},
    'hunan':      {'name': '湖南省', 'zoneId': '430000'},
    'guangdong':  {'name': '广东省', 'zoneId': '440000'},
    'guangxi':    {'name': '广西壮族自治区', 'zoneId': '450000'},
    'hainan':     {'name': '海南省', 'zoneId': '460000'},
    'chongqing':  {'name': '重庆市', 'zoneId': '500000'},
    'sichuan':    {'name': '四川省', 'zoneId': '510000'},
    'guizhou':    {'name': '贵州省', 'zoneId': '520000'},
    'yunnan':     {'name': '云南省', 'zoneId': '530000'},
    'xizang':     {'name': '西藏自治区', 'zoneId': '540000'},
    'shaanxi':    {'name': '陕西省', 'zoneId': '610000'},
    'gansu':      {'name': '甘肃省', 'zoneId': '620000'},
    'qinghai':    {'name': '青海省', 'zoneId': '630000'},
    'ningxia':    {'name': '宁夏回族自治区', 'zoneId': '640000'},
    'xinjiang':   {'name': '新疆维吾尔自治区', 'zoneId': '650000'},
}
