# -*- coding: utf-8 -*-
"""环评公示数据源注册表及各城市常量。

新增条目必须包含 'level' 字段（值为 'province' 或 'city'），用于前端按省级/市级分组展示。
"""
import re

# ------------------------------------------------------------------
# 数据源注册表
# ------------------------------------------------------------------
REGIONS = {
    'guangdong': {
        'name': '广东省',
        'list_url': 'https://gdee.gd.gov.cn/jsxmsp3189/index.html',
        'page_url_pattern': 'https://gdee.gd.gov.cn/jsxmsp3189/index_{page}.html',
        'list_selector': 'ul.i_list',
        'level': 'province',
    },
    'jiangmen': {
        'name': '江门市',
        'list_url': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index.html',
        'page_url_pattern': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index_{page}.html',
        'list_selector': 'ul.infoList',
        'level': 'city',
    },
    'guangzhou': {
        'name': '广州市',
        'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpslgg/',
        'level': 'city',
        'adapter': 'guangzhou',
        'feeds': [
            {'type': 'gz_acceptance_api', 'announcement_type': '受理公告'},
            {
                'type': 'static',
                'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index.html',
                'page_url_pattern': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index_{page}.html',
                'list_selector': 'div.conts-list',
                'item_selector': True,
                'date_selector': 'span:last-child',
                'announcement_type': '审批前公示',
            },
            {
                'type': 'static',
                'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index.html',
                'page_url_pattern': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index_{page}.html',
                'list_selector': 'div.conts-list',
                'item_selector': True,
                'date_selector': 'span:last-child',
                'announcement_type': '批复公告',
            },
        ],
    },
    'dongguan': {
        'name': '东莞市',
        'list_url': 'https://dgepb.dg.gov.cn/zwgk/jsxm/hpspxxgk/slqk/index.html',
        'level': 'city',
        'adapter': 'dongguan',
        'subject_id': '93e889f2501d3fe8015024305bdf0efc',
        'feeds': [
            {
                'dir_id': '402881204e959150014e959f42f30014',
                'date_field': 'HBTB_SLRQ',
                'announcement_type': '受理公告',
            },
            {
                'dir_id': '402881204e959150014e95a16630002c',
                'date_field': 'HBTB_GSSJ',
                'announcement_type': '审批前公示',
            },
            {
                'dir_id': '402881204e959150014e95bb85b5010f',
                'date_field': 'HBTB_GSSJ',
                'announcement_type': '批复公告',
            },
        ],
    },
    'zhuhai': {
        'name': '珠海市',
        'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index.html',
        'level': 'city',
        'feeds': [
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '受理公告',
            },
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/spqgs/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/spqgs/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '审批前公示',
            },
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/sphgg/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/sphgg/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '批复公告',
            },
        ],
    },
    'shenzhen': {
        'name': '深圳市',
        'list_url': 'https://meeb.sz.gov.cn/xxgk/qt/gggs/hpgs/',
        'level': 'city',
        'adapter': 'shenzhen',
        'feeds': [
            {'gstype': 1, 'announcement_type': '受理公告'},
            {'gstype': 2, 'announcement_type': '审批前公示'},
            {'gstype': 3, 'announcement_type': '批复公告'},
        ],
    },
    # --- 以下为新增地级市（2026-07扩展） ---
    'heyuan': {
        'name': '河源市',
        'list_url': 'http://www.heyuan.gov.cn/zwgk/zdlyxx/hjbh/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'zhanjiang': {
        'name': '湛江市',
        'list_url': 'https://www.zhanjiang.gov.cn/zdlyxxgk/sthj/jsxmhjyx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'shaoguan': {
        'name': '韶关市',
        'list_url': 'https://www.sg.gov.cn/zw/zdlyxxgk/dzjg/sgssthjj/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'list_selector': 'div.pageList ul',
        'level': 'city',
    },
    'jieyang': {
        'name': '揭阳市',
        'list_url': 'http://www.jieyang.gov.cn/jyhbj/hjyw/jsxmhbslyspgs/index.html',
        'list_selector': 'ul#lmunes',
        'level': 'city',
    },
    'shanwei': {
        'name': '汕尾市',
        'list_url': 'https://www.shanwei.gov.cn/swhbj/459/515/zdly/hjbh03/index.html',
        'list_selector': 'div.newsclass ul',
        'level': 'city',
    },
    'yangjiang': {
        'name': '阳江市',
        'list_url': 'http://www.yangjiang.gov.cn/yj/zwgk/zdlyxxgk/hjbh/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'shantou': {
        'name': '汕头市',
        'list_url': 'https://www.shantou.gov.cn/cnst/zdly/hjbhxxgk/index.html',
        'list_selector': 'div.list_div',
        'item_selector': True,
        'level': 'city',
    },
    'huizhou': {
        'name': '惠州市',
        'list_url': 'http://www.huizhou.gov.cn/zdlyxxgk/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'foshan': {
        'name': '佛山市',
        'list_url': 'http://sthj.foshan.gov.cn/hjyxpj/hpspgs/hpslgg/index.html',
        'list_selector': 'div.list-content2',
        'level': 'city',
    },
    'zhongshan': {
        'name': '中山市',
        'list_url': 'http://zsepb.zs.gov.cn/xxml/ztzl/gcjslyxmxx/ssthjjhpspgs/slgs/index.html',
        'list_selector': 'ul.pub_list',
        'level': 'city',
    },
    'yunfu': {
        'name': '云浮市',
        'list_url': 'https://www.yunfu.gov.cn/sthjj/zdlyxxgkzl/jsxmhjyxpj/slgg/index.html',
        'list_selector': 'div.nyrtct ul',
        'level': 'city',
    },
    'maoming': {
        'name': '茂名市',
        'list_url': 'http://www.maoming.gov.cn/zwgk/zwzl/zdlyxxgkzl/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'page_url_pattern': 'http://www.maoming.gov.cn/zwgk/zwzl/zdlyxxgkzl/hjbhxxgk/jsxmhjyxpjxx/index_{page}.html',
        'list_selector': 'div.common-list',
        'level': 'city',
    },
    'zhaoqing': {
        'name': '肇庆市',
        'list_url': 'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/index',
        'level': 'city',
        'adapter': 'zhaoqing',
        'feeds': [
            {'column_id': 21023, 'announcement_type': '受理公告'},
            {'column_id': 21025, 'announcement_type': '审批前公示'},
            {'column_id': 21028, 'announcement_type': '审批后公告'},
        ],
    },
}

# ------------------------------------------------------------------
# 广州常量
# ------------------------------------------------------------------
_GUANGZHOU_API_BASE = 'http://112.94.69.56:8066'
_GUANGZHOU_LIST_URL = _GUANGZHOU_API_BASE + '/api/hpslgl/getListPublished'
_GUANGZHOU_DETAIL_URL = _GUANGZHOU_API_BASE + '/api/hpslgl/detail'
_GUANGZHOU_DETAIL_PAGE = _GUANGZHOU_API_BASE + '/#/hpslzs/index'
_GUANGZHOU_PAGE_SIZE = 100

# ------------------------------------------------------------------
# 东莞常量
# ------------------------------------------------------------------
_DONGGUAN_LIST_URL = 'https://dgstsjzx.dg.cn/hbgs/zwgk/item.do'
_DONGGUAN_DETAIL_URL = 'https://dgstsjzx.dg.cn/hbgs/zwgk/view.do'
_DONGGUAN_PAGE_SIZE = 20
_DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA = 3
_DONGGUAN_MAX_RESULTS_PER_SLICE = _DONGGUAN_PAGE_SIZE * _DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA
_DONGGUAN_NUMBER_MIN = 0
_DONGGUAN_NUMBER_MAX = 99_999_999_999
_DONGGUAN_MAX_SPLIT_DEPTH = 48

# ------------------------------------------------------------------
# 深圳常量
# ------------------------------------------------------------------
_SHENZHEN_BASE = 'https://ep.meeb.sz.gov.cn:8443'
_SHENZHEN_LIST_URL = _SHENZHEN_BASE + '/HP_SZ_OUT/publicity/approval_public_list/{gstype}.vm'
_SHENZHEN_DETAIL_URL = _SHENZHEN_BASE + '/HP_SZ_OUT/htmltemp/html/{pkid}_{gstype}.html'
_SHENZHEN_PAGE_SIZE = 10
_SHENZHEN_DOREAD_RE = re.compile(r"doRead\('([0-9a-fA-F]{32})'\s*,\s*'(\d+)'\)")

# ------------------------------------------------------------------
# 肇庆常量
# ------------------------------------------------------------------
_ZHAOQING_APP_URL = 'https://www.zhaoqing.gov.cn/zqhjj'
_ZHAOQING_API_URL = _ZHAOQING_APP_URL + '/gkmlpt/api/all/{column_id}?page=1&sid=758019'
_ZHAOQING_DETAIL_RE = re.compile(r'DETAIL:\s*({.*?})\s*,\s*TREE:')
_ZHAOQING_FULL_THRESHOLD = 50