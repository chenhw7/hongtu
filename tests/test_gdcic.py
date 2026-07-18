# -*- coding: utf-8 -*-
"""gdcic 采集模块单元测试。

仅测试纯函数解析逻辑，不测试真实 Playwright 页面操作（依赖网络）。
"""
import pytest
from datetime import date


# ------------------------------------------------------------------
# parser 测试 — API JSON 解析
# ------------------------------------------------------------------

MOCK_API_ROWS = [
    {
        'projectName': 'XX市供水管网改造工程管材采购',
        'projectCode': 'GDCIC-2026-001',
        'typeName': '招标公告',
        'ownerName': 'XX市自来水有限公司',
        'areaName': '广东省江门市',
        'contactPerson': '张三',
        'contactPhone': '0750-12345678',
        'budgetAmount': '150万元',
        'publishDate': '2026-07-15',
        'url': '/detail/10001.html',
    },
    {
        'name': 'YY县雨污分流工程HDPE双壁波纹管采购',
        'code': 'GDCIC-2026-002',
        'category': '中标公告',
        'buyerName': 'YY县住建局',
        'city': '广州市',
        'phone': '020-87654321',
        'amount': '200万元',
        'createTime': '2026/07/14',
        'detailUrl': 'https://skypt.gdcic.net/detail/10002.html',
    },
    {
        'title': 'ZZ污水处理厂管道维修工程',
        'type': '资格预审',
        'jsdw': 'ZZ市排水管理处',
        'dq': '深圳市',
        'lxr': '李四',
        'lxdh': '13812345678',
        'fbDate': '2026年7月13日',
    },
]


class TestParseApiList:
    """测试 API JSON 解析。"""

    def test_parse_api_list_basic(self):
        from scraper.gdcic.parser import parse_api_list
        results = parse_api_list(MOCK_API_ROWS)
        assert len(results) == 3

        # 第 1 条
        r0 = results[0]
        assert r0['project_name'] == 'XX市供水管网改造工程管材采购'
        assert r0['bidding_number'] == 'GDCIC-2026-001'
        assert r0['announcement_type'] == '招标公告'
        assert r0['buyer_name'] == 'XX市自来水有限公司'
        assert '江门' in r0['region']
        assert r0['contact_person'] == '张三'
        assert r0['phone'] == '0750-12345678'
        assert r0['publish_date'] == date(2026, 7, 15)

    def test_parse_api_list_alt_keys(self):
        from scraper.gdcic.parser import parse_api_list
        results = parse_api_list(MOCK_API_ROWS)

        # 第 2 条 — 使用备选字段名
        r1 = results[1]
        assert '雨污分流' in r1['project_name']
        assert r1['buyer_name'] == 'YY县住建局'
        assert r1['phone'] == '020-87654321'

    def test_parse_api_list_source_url(self):
        from scraper.gdcic.parser import parse_api_list
        results = parse_api_list(MOCK_API_ROWS)

        # 相对 URL 应拼接 base_url
        r0 = results[0]
        assert r0['source_url'].startswith('https://www.gdcic.net')

        # 绝对 URL 保持不变
        r1 = results[1]
        assert r1['source_url'] == 'https://skypt.gdcic.net/detail/10002.html'

    def test_parse_api_list_date_formats(self):
        from scraper.gdcic.parser import parse_api_list
        results = parse_api_list(MOCK_API_ROWS)

        # 中文日期
        r2 = results[2]
        assert r2['publish_date'] == date(2026, 7, 13)

    def test_parse_api_list_empty(self):
        from scraper.gdcic.parser import parse_api_list
        assert parse_api_list([]) == []
        assert parse_api_list(None) == []

    def test_parse_api_list_non_dict_rows(self):
        from scraper.gdcic.parser import parse_api_list
        rows = ['not a dict', 123, None, {'projectName': 'Test Project'}]
        results = parse_api_list(rows)
        assert len(results) == 1
        assert results[0]['project_name'] == 'Test Project'


# ------------------------------------------------------------------
# parser 测试 — DOM 解析
# ------------------------------------------------------------------

MOCK_DOM_HTML_TABLE = """
<html><body>
<table class="el-table__body">
<thead><tr>
    <th>项目名称</th><th>建设单位</th><th>地区</th><th>发布日期</th>
</tr></thead>
<tbody>
    <tr>
        <td><a href="/detail/2001.html">XX市供水管网改造工程</a></td>
        <td>XX市自来水公司</td>
        <td>江门市</td>
        <td>2026-07-15</td>
    </tr>
    <tr>
        <td><a href="/detail/2002.html">YY县雨污分流工程</a></td>
        <td>YY县住建局</td>
        <td>广州市</td>
        <td>2026-07-14</td>
    </tr>
</tbody>
</table>
</body></html>
"""

MOCK_DOM_HTML_LIST = """
<html><body>
<div class="list-container">
    <div class="item">
        <a href="/detail/3001.html">ZZ污水处理厂管道维修工程招标公告</a>
        <span class="date">2026-07-13</span>
        <span class="type">招标公告</span>
    </div>
    <div class="item">
        <a href="/detail/3002.html">WW市政道路管道铺设项目</a>
        <span class="date">2026-07-12</span>
        <span class="type">中标公告</span>
    </div>
</div>
</body></html>
"""


class TestParseDomList:
    """测试 DOM 解析。"""

    def test_parse_dom_table(self):
        from scraper.gdcic.parser import parse_dom_list
        results = parse_dom_list(MOCK_DOM_HTML_TABLE)
        assert len(results) >= 2

        assert '供水管网' in results[0]['project_name']
        assert results[0]['source_url'].endswith('/detail/2001.html')

    def test_parse_dom_list_items(self):
        from scraper.gdcic.parser import parse_dom_list
        results = parse_dom_list(MOCK_DOM_HTML_LIST)
        assert len(results) >= 2

        assert '污水处理' in results[0]['project_name']
        assert results[0]['announcement_type'] == '招标公告'

    def test_parse_dom_empty(self):
        from scraper.gdcic.parser import parse_dom_list
        assert parse_dom_list('') == []
        assert parse_dom_list(None) == []
        assert parse_dom_list('<html><body></body></html>') == []


# ------------------------------------------------------------------
# utils 测试
# ------------------------------------------------------------------

class TestCleanGdcicText:
    """测试文本清理函数。"""

    def test_clean_text(self):
        from scraper.gdcic.utils import clean_gdcic_text
        assert clean_gdcic_text('') == ''
        assert clean_gdcic_text(None) == ''
        assert clean_gdcic_text('  hello  world  ') == 'hello world'
        assert clean_gdcic_text('line1\n  line2\t  line3') == 'line1 line2 line3'


class TestParseGdcicDate:
    """测试日期解析函数。"""

    def test_parse_date_standard(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026-07-18')
        assert d == date(2026, 7, 18)
        assert t is None

    def test_parse_date_with_time(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026-07-18 10:30:00')
        assert d == date(2026, 7, 18)
        assert t == '10:30:00'

    def test_parse_date_slash(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026/07/18')
        assert d == date(2026, 7, 18)

    def test_parse_date_chinese(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026年7月18日')
        assert d == date(2026, 7, 18)

    def test_parse_date_empty(self):
        from scraper.gdcic.utils import parse_gdcic_date
        assert parse_gdcic_date('') == (None, None)
        assert parse_gdcic_date(None) == (None, None)


class TestExtractGdcicPhone:
    """测试电话提取函数。"""

    def test_landline(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('电话：0750-12345678') == '0750-12345678'

    def test_mobile(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('联系人手机：13812345678') == '13812345678'

    def test_no_phone(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('') == ''
        assert extract_gdcic_phone(None) == ''
        assert extract_gdcic_phone('没有电话') == ''


# ------------------------------------------------------------------
# browser 辅助函数测试
# ------------------------------------------------------------------

class TestBrowserHelpers:
    """测试 browser.py 中的纯函数。"""

    def test_is_api_candidate(self):
        from scraper.gdcic.browser import _is_api_candidate
        assert _is_api_candidate('https://skypt.gdcic.net/api/queryData') is True
        assert _is_api_candidate('https://skypt.gdcic.net/openplatform/search') is True
        assert _is_api_candidate('https://cdn.example.com/app.js') is False
        assert _is_api_candidate('https://cdn.example.com/logo.png') is False
        assert _is_api_candidate('') is False
        assert _is_api_candidate(None) is False

    def test_has_signature_params(self):
        from scraper.gdcic.browser import _has_signature_params
        assert _has_signature_params('https://api.example.com/data?sign=abc123') is True
        assert _has_signature_params('https://api.example.com/data?token=xyz') is True
        assert _has_signature_params('https://api.example.com/data?page=1&size=20') is False
        assert _has_signature_params('https://api.example.com/data') is False

    def test_make_cache_key(self):
        from scraper.gdcic.browser import GdcicBrowser
        key = GdcicBrowser._make_cache_key(
            'https://skypt.gdcic.net/api/search?keyword=test&page=1', 'GET'
        )
        assert key == 'GET:/api/search'


# ------------------------------------------------------------------
# registry 测试
# ------------------------------------------------------------------

class TestRegistry:
    """测试 registry 注册。"""

    def test_registry_has_gdcic(self):
        from scraper.registry import SCRAPER_REGISTRY
        assert 'gdcic' in SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['gdcic']
        assert entry['label'] == '广东住建厅'
        assert entry['class_name'] == 'GdcicScraper'
        assert entry['badge_class'] == 'badge-indigo'
        assert entry['include_in_all'] is True
        assert entry['is_lead_source'] is True
        assert 'gdcic.net' in entry['source_site']

    def test_scraper_class_import(self):
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('gdcic')
        assert cls is not None
        assert cls.__name__ == 'GdcicScraper'

    def test_scraper_source_type(self):
        from scraper.gdcic import GdcicScraper
        assert GdcicScraper.source_type == 'gdcic'
        assert 'gdcic.net' in GdcicScraper.base_url

    def test_config_source_sites(self):
        from app.config import Config
        sites = Config.SCRAPER_SOURCE_SITES
        assert 'gdcic' in sites
        assert 'gdcic.net' in sites['gdcic']
