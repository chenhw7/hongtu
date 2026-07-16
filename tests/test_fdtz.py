# -*- coding: utf-8 -*-
"""fdtz 采集模块单元测试。

覆盖范围：
- parser: 列表项字段映射（备案/核准/审批）
- parser: 详情字段解析
- utils: 日期解析、投资金额解析
- registry: fdtz 条目验证
- import: 模块导入验证
"""
import pytest


# ------------------------------------------------------------------
# utils: parse_fdtz_date
# ------------------------------------------------------------------
class TestParseFdtzDate:
    def setup_method(self):
        from scraper.fdtz.utils import parse_fdtz_date
        self.parse = parse_fdtz_date

    def test_none(self):
        assert self.parse(None) == ('', '')

    def test_empty_string(self):
        assert self.parse('') == ('', '')

    def test_iso_date(self):
        d, t = self.parse('2024-06-15')
        assert d == '2024-06-15'
        assert t == ''

    def test_iso_datetime(self):
        d, t = self.parse('2024-06-15 14:30:00')
        assert d == '2024-06-15'
        assert t == '14:30:00'

    def test_timestamp_ms_int(self):
        # 2024-01-01 00:00:00 UTC = 1704067200000 ms
        d, t = self.parse(1704067200000)
        # 验证格式正确，时区可能影响具体日期
        assert len(d) == 10
        assert d[:4] in ('2023', '2024')

    def test_timestamp_ms_str(self):
        d, t = self.parse('1704067200000')
        assert len(d) == 10

    def test_timestamp_s_str(self):
        d, t = self.parse('1704067200')
        assert len(d) == 10

    def test_compact_yyyymmdd(self):
        d, t = self.parse('20240615')
        assert d == '2024-06-15'
        assert t == ''

    def test_chinese_date(self):
        d, t = self.parse('2024年06月15日')
        assert d == '2024-06-15'
        assert t == ''

    def test_slash_date(self):
        d, t = self.parse('2024/06/15')
        assert d == '2024-06-15'
        assert t == ''

    def test_invalid_string(self):
        d, t = self.parse('not-a-date')
        assert d == ''
        assert t == ''


# ------------------------------------------------------------------
# utils: parse_investment
# ------------------------------------------------------------------
class TestParseInvestment:
    def setup_method(self):
        from scraper.fdtz.utils import parse_investment
        self.parse = parse_investment

    def test_none(self):
        assert self.parse(None) is None

    def test_empty_string(self):
        assert self.parse('') is None

    def test_numeric_wan(self):
        # 1500 万元 = 15000000 元
        result = self.parse(1500)
        assert result == 1500 * 10000

    def test_float_wan(self):
        result = self.parse(1500.5)
        assert result == 1500.5 * 10000

    def test_string_wan(self):
        result = self.parse('1500.00')
        assert result == 1500.0 * 10000

    def test_string_with_unit_wan(self):
        result = self.parse('1500万元')
        assert result == 1500 * 10000

    def test_string_with_unit_yi(self):
        result = self.parse('2亿元')
        assert result == 2 * 100000000

    def test_string_with_unit_yuan(self):
        result = self.parse('5000000元')
        assert result == 5000000

    def test_zero(self):
        assert self.parse(0) is None

    def test_invalid_string(self):
        assert self.parse('abc') is None

    def test_comma_separated(self):
        result = self.parse('1,500.00')
        assert result == 1500.0 * 10000


# ------------------------------------------------------------------
# parser: parse_list_item
# ------------------------------------------------------------------
class TestParserListItemBA:
    """备案项目字段映射测试。"""

    def setup_method(self):
        from scraper.fdtz.parser import parse_list_item
        self.parse = parse_list_item

    def test_basic_ba_item(self):
        item = {
            'baId': 'BA001',
            'proofCode': '2024-440000-01',
            'projectName': '广州市某污水处理厂建设项目',
            'applyOrgan': '广州市水务局',
            'place': '广州市',
            'totalInvest': 1500.0,
            'finishDate': '2024-06-15',
        }
        lead = self.parse(item, 'ba')
        assert lead['project_name'] == '广州市某污水处理厂建设项目'
        assert lead['bidding_number'] == '2024-440000-01'
        assert lead['buyer_name'] == '广州市水务局'
        assert lead['region'] == '广州市'
        assert lead['budget_amount'] == 1500.0 * 10000
        assert lead['publish_date'] == '2024-06-15'
        assert lead['announcement_type'] == '备案项目'
        assert lead['_item_id'] == 'BA001'
        assert lead['_category'] == 'ba'
        assert 'source_url' in lead

    def test_ba_item_missing_fields(self):
        item = {
            'baId': 'BA002',
            'projectName': '某项目',
        }
        lead = self.parse(item, 'ba')
        assert lead['project_name'] == '某项目'
        assert lead.get('buyer_name', '') == ''
        assert lead.get('budget_amount') is None


class TestParserListItemHZ:
    """核准项目字段映射测试。"""

    def setup_method(self):
        from scraper.fdtz.parser import parse_list_item
        self.parse = parse_list_item

    def test_hz_gg_item(self):
        item = {
            'id': 'HZ001',
            'projectCode': 'GD-2024-001',
            'pname': '深圳市某综合管廊工程',
            'buildOrgan': '深圳市工务署',
            'place': '深圳市',
            'totalInvest': 8000,
            'finishDate': '2024-07-01',
        }
        lead = self.parse(item, 'hz_gg')
        assert lead['project_name'] == '深圳市某综合管廊工程'
        assert lead['bidding_number'] == 'GD-2024-001'
        assert lead['buyer_name'] == '深圳市工务署'
        assert lead['region'] == '深圳市'
        assert lead['budget_amount'] == 8000 * 10000
        assert lead['announcement_type'] == '核准公告'
        assert lead['_item_id'] == 'HZ001'
        assert lead['_category'] == 'hz_gg'

    def test_hz_gs_item(self):
        item = {
            'id': 'HZ002',
            'projectCode': 'GD-2024-002',
            'projectName': '珠海市某给水工程',
            'buildOrgan': '珠海市水务局',
            'place': '珠海市',
        }
        lead = self.parse(item, 'hz_gs')
        assert lead['project_name'] == '珠海市某给水工程'
        assert lead['announcement_type'] == '核准公示'


# ------------------------------------------------------------------
# parser: parse_detail
# ------------------------------------------------------------------
class TestParserDetail:
    def setup_method(self):
        from scraper.fdtz.parser import parse_detail
        self.parse = parse_detail

    def test_detail_with_data_wrapper(self):
        detail_data = {
            'code': 0,
            'data': {
                'projectCode': 'SP-2024-001',
                'projectName': '佛山市某污水处理厂扩建工程',
                'buildOrgan': '佛山市水务局',
                'place': '佛山市',
                'totalInvest': 3500,
                'finishDate': '2024-08-01',
                'approvalNo': '佛发改审〔2024〕100号',
                'buildContent': '新建污水处理厂一座，日处理能力5万吨',
            }
        }
        extra = self.parse(detail_data, 'sp_gg')
        assert extra['bidding_number'] == 'SP-2024-001'
        assert extra['project_name'] == '佛山市某污水处理厂扩建工程'
        assert extra['buyer_name'] == '佛山市水务局'
        assert extra['region'] == '佛山市'
        assert extra['budget_amount'] == 3500 * 10000
        assert extra['publish_date'] == '2024-08-01'
        assert extra['approval_no'] == '佛发改审〔2024〕100号'
        assert 'description' in extra

    def test_detail_none(self):
        assert self.parse(None, 'ba') == {}

    def test_detail_flat_structure(self):
        detail_data = {
            'projectCode': 'BA-2024-099',
            'projectName': '东莞市某工业园区项目',
            'applyOrgan': '东莞市工信局',
        }
        extra = self.parse(detail_data, 'ba')
        assert extra['bidding_number'] == 'BA-2024-099'
        assert extra['project_name'] == '东莞市某工业园区项目'
        assert extra['buyer_name'] == '东莞市工信局'


# ------------------------------------------------------------------
# registry
# ------------------------------------------------------------------
class TestRegistryHasFdtz:
    def test_fdtz_in_registry(self):
        from scraper.registry import SCRAPER_REGISTRY
        assert 'fdtz' in SCRAPER_REGISTRY

    def test_fdtz_registry_fields(self):
        from scraper.registry import SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['fdtz']
        assert entry['label'] == '发改委项目审批'
        assert entry['import_path'] == 'scraper.fdtz'
        assert entry['class_name'] == 'FdtzScraper'
        assert entry['badge_class'] == 'badge-purple'
        assert entry['include_in_all'] is True
        assert entry['is_lead_source'] is True
        assert entry['source_site'] == 'https://tzxm.gd.gov.cn/'

    def test_fdtz_in_source_sites(self):
        from scraper.registry import get_source_sites
        sites = get_source_sites()
        assert 'fdtz' in sites
        assert sites['fdtz'] == 'https://tzxm.gd.gov.cn/'


# ------------------------------------------------------------------
# import
# ------------------------------------------------------------------
class TestScraperClassImport:
    def test_import_fdtz_module(self):
        import scraper.fdtz
        assert hasattr(scraper.fdtz, 'FdtzScraper')

    def test_import_via_registry(self):
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('fdtz')
        assert cls is not None
        assert cls.__name__ == 'FdtzScraper'

    def test_scraper_source_type(self):
        from scraper.fdtz import FdtzScraper
        assert FdtzScraper.source_type == 'fdtz'
        assert FdtzScraper.base_url == 'https://tzxm.gd.gov.cn'

    def test_scraper_default_keywords(self):
        from scraper.fdtz import FdtzScraper
        scraper = FdtzScraper()
        kws = scraper.default_keywords()
        assert len(kws) > 0
        assert any(kw.startswith('channel:') for kw in kws)
        # 应包含项目类型词（如"污水处理厂"）
        assert any('污水' in kw for kw in kws)

    def test_keyword_display(self):
        from scraper.fdtz import FdtzScraper
        scraper = FdtzScraper()
        assert scraper._keyword_display('channel:ba') == '备案项目'
        assert scraper._keyword_display('channel:hz') == '核准项目'
        assert scraper._keyword_display('channel:sp') == '审批项目'
        assert scraper._keyword_display('污水处理厂') == '污水处理厂'
