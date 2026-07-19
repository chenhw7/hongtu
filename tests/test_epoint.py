# -*- coding: utf-8 -*-
"""EpointWebBuilder 通用模块 + 浙江 ggzyjy 适配器单元测试。"""
import unittest
from datetime import date
from unittest.mock import patch, MagicMock


class TestEpointDateParser(unittest.TestCase):
    """验证 epoint 日期解析。"""

    def test_full_datetime(self):
        """验证 'YYYY-MM-DD HH:MM:SS' 格式。"""
        from scraper.epoint.utils import parse_epoint_date
        d, t = parse_epoint_date('2026-07-17 23:54:47')
        self.assertEqual(d, date(2026, 7, 17))
        self.assertEqual(t, '23:54')

    def test_date_only(self):
        """验证仅日期格式。"""
        from scraper.epoint.utils import parse_epoint_date
        d, t = parse_epoint_date('2026-07-17')
        self.assertEqual(d, date(2026, 7, 17))
        self.assertIsNone(t)

    def test_chinese_date(self):
        """验证中文日期格式。"""
        from scraper.epoint.utils import parse_epoint_date
        d, t = parse_epoint_date('2026年07月17日')
        self.assertEqual(d, date(2026, 7, 17))

    def test_empty_input(self):
        """验证空输入返回 None。"""
        from scraper.epoint.utils import parse_epoint_date
        d, t = parse_epoint_date('')
        self.assertIsNone(d)
        self.assertIsNone(t)
        d, t = parse_epoint_date(None)
        self.assertIsNone(d)
        self.assertIsNone(t)


class TestEpointBudget(unittest.TestCase):
    """验证 epoint 金额解析。"""

    def test_wan_yuan(self):
        from scraper.epoint.utils import parse_budget
        self.assertEqual(parse_budget('投资金额：387.5万元'), 3875000.0)

    def test_yuan(self):
        from scraper.epoint.utils import parse_budget
        self.assertAlmostEqual(parse_budget('预算金额 1234567.89 元'), 1234567.89)

    def test_yi_yuan(self):
        from scraper.epoint.utils import parse_budget
        self.assertEqual(parse_budget('合同估算价 1.5亿元'), 150000000.0)

    def test_no_match(self):
        from scraper.epoint.utils import parse_budget
        self.assertIsNone(parse_budget('无金额信息'))
        self.assertIsNone(parse_budget(''))
        self.assertIsNone(parse_budget(None))


class TestCleanHtmlText(unittest.TestCase):
    """验证 HTML 清洗工具。"""

    def test_strip_tags(self):
        from scraper.epoint.utils import clean_html_text
        result = clean_html_text('<p>招标公告</p><b>内容</b>')
        self.assertEqual(result, '招标公告 内容')

    def test_empty_input(self):
        from scraper.epoint.utils import clean_html_text
        self.assertEqual(clean_html_text(''), '')
        self.assertEqual(clean_html_text(None), '')


class TestEpointParseRecord(unittest.TestCase):
    """验证 parser.parse_record() 字段映射。"""

    def _make_scraper(self):
        """构造一个模拟的 scraper 实例。"""
        scraper = MagicMock()
        scraper.base_url = 'https://ggzy.zj.gov.cn'
        scraper.REGIONS = {
            '330501': {'name': '湖州市'},
        }
        return scraper

    def test_parse_record_basic(self):
        """验证基本字段映射。"""
        from scraper.epoint.parser import parse_record

        mock_record = {
            'title': '湖州市某供水管网改造工程施工招标公告',
            'webdate': '2026-07-17 23:54:47',
            'infod': '湖州市',
            'infoc': '330501',
            'infoa': 'A01',
            'infob': 'A',
            'linkurl': '/jyxxgk/002001/002001001/20260717/abc-123.html',
            'categorynum': '002001001',
            'categoryname': '招标公告',
            'content': '<p>招标内容</p>',
        }

        scraper = self._make_scraper()
        lead = parse_record(mock_record, scraper)

        self.assertEqual(lead['project_name'], '湖州市某供水管网改造工程施工招标公告')
        self.assertEqual(lead['announcement_type'], '招标公告')
        self.assertEqual(lead['region'], '湖州市')  # 通过 infoc 匹配 REGIONS
        self.assertEqual(lead['publish_date'], date(2026, 7, 17))
        self.assertEqual(lead['publish_time'], '23:54')
        self.assertIn('source_url', lead)
        self.assertIn('ggzy.zj.gov.cn', lead['source_url'])
        self.assertIn('_detail_path', lead)
        self.assertEqual(lead['content'], '招标内容')

    def test_parse_record_empty_title(self):
        """验证空标题返回 None。"""
        from scraper.epoint.parser import parse_record

        scraper = self._make_scraper()
        result = parse_record({'title': '', 'webdate': '2026-07-17'}, scraper)
        self.assertIsNone(result)

    def test_parse_record_no_region_match(self):
        """验证未匹配到 REGIONS 时使用 infod 原始值。"""
        from scraper.epoint.parser import parse_record

        mock_record = {
            'title': '某项目招标公告',
            'webdate': '2026-07-17',
            'infod': '未知地区',
            'infoc': '999999',
            'linkurl': '/test.html',
            'categoryname': '招标公告',
            'content': '',
        }

        scraper = self._make_scraper()
        lead = parse_record(mock_record, scraper)
        self.assertEqual(lead['region'], '未知地区')


class TestZjGgzyjyScraper(unittest.TestCase):
    """验证浙江爬虫类。"""

    def test_import_and_instantiate(self):
        """验证 ZjGgzyjyScraper 可以正常导入和实例化。"""
        from scraper.ggzyjy_zj import ZjGgzyjyScraper
        scraper = ZjGgzyjyScraper()
        self.assertEqual(scraper.source_type, 'ggzyjy_zj')
        self.assertEqual(scraper.base_url, 'https://ggzy.zj.gov.cn')
        self.assertEqual(scraper.CATEGORY_NUM, '002001001')
        self.assertEqual(scraper.TIME_FIELD, 'webdate')
        self.assertEqual(len(scraper.REGIONS), 11)

    def test_inherits_from_epoint_base(self):
        """验证继承关系正确。"""
        from scraper.ggzyjy_zj import ZjGgzyjyScraper
        from scraper.epoint import EpointBaseScraper
        self.assertTrue(issubclass(ZjGgzyjyScraper, EpointBaseScraper))

    def test_keywords_loaded(self):
        """验证关键词已加载。"""
        from scraper.ggzyjy_zj import ZjGgzyjyScraper
        scraper = ZjGgzyjyScraper()
        self.assertTrue(len(scraper.keywords) > 0)
        # 应包含管道相关关键词
        self.assertIn('管道', scraper.keywords)


class TestZjRegions(unittest.TestCase):
    """验证浙江地区码配置。"""

    def test_regions_count(self):
        """验证包含 11 个地市。"""
        from scraper.ggzyjy_zj.regions import REGIONS
        self.assertEqual(len(REGIONS), 11)

    def test_known_cities(self):
        """验证已知城市编码。"""
        from scraper.ggzyjy_zj.regions import REGIONS
        self.assertEqual(REGIONS['330101']['name'], '杭州市')
        self.assertEqual(REGIONS['330201']['name'], '宁波市')
        self.assertEqual(REGIONS['330501']['name'], '湖州市')

    def test_all_codes_start_with_33(self):
        """验证所有地区码以 33 开头。"""
        from scraper.ggzyjy_zj.regions import REGIONS
        for code in REGIONS:
            self.assertTrue(code.startswith('33'), f'{code} 应以 33 开头')


class TestRegistryHasGgzyjyZj(unittest.TestCase):
    """验证 registry 注册。"""

    def test_registry_entry(self):
        """验证 SCRAPER_REGISTRY 包含 ggzyjy_zj 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('ggzyjy_zj', SCRAPER_REGISTRY)
        entry = SCRAPER_REGISTRY['ggzyjy_zj']
        self.assertEqual(entry['label'], '浙江公共资源交易')
        self.assertEqual(entry['import_path'], 'scraper.ggzyjy_zj')
        self.assertEqual(entry['class_name'], 'ZjGgzyjyScraper')
        self.assertTrue(entry['include_in_all'])
        self.assertTrue(entry['is_lead_source'])

    def test_dynamic_import(self):
        """验证通过 registry 动态加载无 ImportError。"""
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('ggzyjy_zj')
        self.assertIsNotNone(cls)
        from scraper.ggzyjy_zj import ZjGgzyjyScraper
        self.assertIs(cls, ZjGgzyjyScraper)


class TestEpointSearchBody(unittest.TestCase):
    """验证搜索请求体构建。"""

    def test_build_search_body(self):
        """验证 POST 请求体参数正确。"""
        from scraper.epoint.search import _build_search_body

        scraper = MagicMock()
        scraper.PAGE_SIZE = 20
        scraper.CATEGORY_NUM = '002001001'
        scraper.TIME_FIELD = 'webdate'

        body = _build_search_body('管道', 1, scraper)

        self.assertEqual(body['pn'], 0)       # 第1页起始行=0
        self.assertEqual(body['rn'], '20')
        self.assertEqual(body['wd'], '管道')
        self.assertEqual(body['cnum'], '002001001')
        self.assertEqual(body['isBusiness'], '1')
        self.assertIn('webdate', body['sort'])
        self.assertTrue(len(body['time']) == 1)
        self.assertEqual(body['time'][0]['fieldName'], 'webdate')

    def test_build_search_body_page2(self):
        """验证第2页的起始行计算。"""
        from scraper.epoint.search import _build_search_body

        scraper = MagicMock()
        scraper.PAGE_SIZE = 20
        scraper.CATEGORY_NUM = '002001001'
        scraper.TIME_FIELD = 'webdate'

        body = _build_search_body('', 2, scraper)
        self.assertEqual(body['pn'], 20)      # 第2页起始行=20
        self.assertEqual(body['wd'], '')


class TestEpointProcessPage(unittest.TestCase):
    """验证搜索结果处理。"""

    def test_process_page_empty_payload(self):
        """验证空 payload 返回 None。"""
        from scraper.epoint.search import _process_page
        scraper = MagicMock()
        result = _process_page(scraper, None)
        self.assertIsNone(result)

    def test_process_page_no_records(self):
        """验证无记录时返回空列表。"""
        from scraper.epoint.search import _process_page
        scraper = MagicMock()
        result = _process_page(scraper, {'result': {'totalcount': 0, 'records': []}})
        self.assertEqual(result, [])


class TestScGgzyjyScraper(unittest.TestCase):
    """验证四川爬虫类。"""

    def test_import_and_instantiate(self):
        """验证 ScGgzyjyScraper 可以正常导入和实例化。"""
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        scraper = ScGgzyjyScraper()
        self.assertEqual(scraper.source_type, 'ggzyjy_sc')
        self.assertEqual(scraper.base_url, 'https://ggzyjy.sc.gov.cn')
        self.assertEqual(scraper.CATEGORY_NUM, '001')
        self.assertEqual(scraper.TIME_FIELD, 'infodatepx')
        self.assertEqual(len(scraper.REGIONS), 21)

    def test_inherits_from_epoint_base(self):
        """验证继承关系正确。"""
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        from scraper.epoint import EpointBaseScraper
        self.assertTrue(issubclass(ScGgzyjyScraper, EpointBaseScraper))

    def test_keywords_loaded(self):
        """验证关键词已加载。"""
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        scraper = ScGgzyjyScraper()
        self.assertTrue(len(scraper.keywords) > 0)
        self.assertIn('管道', scraper.keywords)

    def test_referers_configured(self):
        """验证 REFERERS 列表已配置且 get_random_referer 返回有效值。"""
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        scraper = ScGgzyjyScraper()
        self.assertEqual(len(scraper.REFERERS), 5)
        referer = scraper.get_random_referer()
        self.assertIn(referer, scraper.REFERERS)


class TestScRegions(unittest.TestCase):
    """验证四川地区码配置。"""

    def test_regions_count(self):
        """验证包含 21 个市州。"""
        from scraper.ggzyjy_sc.regions import REGIONS
        self.assertEqual(len(REGIONS), 21)

    def test_known_cities(self):
        """验证已知城市编码。"""
        from scraper.ggzyjy_sc.regions import REGIONS
        self.assertEqual(REGIONS['510101']['name'], '成都市')
        self.assertEqual(REGIONS['510701']['name'], '绵阳市')
        self.assertEqual(REGIONS['513401']['name'], '凉山州')

    def test_all_codes_start_with_51(self):
        """验证所有地区码以 51 开头。"""
        from scraper.ggzyjy_sc.regions import REGIONS
        for code in REGIONS:
            self.assertTrue(code.startswith('51'), f'{code} 应以 51 开头')


class TestRegistryHasGgzyjySc(unittest.TestCase):
    """验证 registry 四川注册。"""

    def test_registry_entry(self):
        """验证 SCRAPER_REGISTRY 包含 ggzyjy_sc 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('ggzyjy_sc', SCRAPER_REGISTRY)
        entry = SCRAPER_REGISTRY['ggzyjy_sc']
        self.assertEqual(entry['label'], '四川公共资源交易')
        self.assertEqual(entry['import_path'], 'scraper.ggzyjy_sc')
        self.assertEqual(entry['class_name'], 'ScGgzyjyScraper')
        self.assertTrue(entry['include_in_all'])
        self.assertTrue(entry['is_lead_source'])

    def test_dynamic_import(self):
        """验证通过 registry 动态加载无 ImportError。"""
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('ggzyjy_sc')
        self.assertIsNotNone(cls)
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        self.assertIs(cls, ScGgzyjyScraper)


class TestJsGgzyjyScraper(unittest.TestCase):
    """验证江苏爬虫类。"""

    def test_inherits_from_epoint_base(self):
        """验证继承关系正确。"""
        from scraper.ggzyjy_js import JsGgzyjyScraper
        from scraper.epoint import EpointBaseScraper
        self.assertTrue(issubclass(JsGgzyjyScraper, EpointBaseScraper))

    def test_import_and_instantiate(self):
        """验证 JsGgzyjyScraper 可以正常导入和实例化，关键差异配置正确。"""
        from scraper.ggzyjy_js import JsGgzyjyScraper
        scraper = JsGgzyjyScraper()
        self.assertEqual(scraper.source_type, 'ggzyjy_js')
        self.assertEqual(scraper.base_url, 'http://jsggzy.jszwfw.gov.cn')
        self.assertEqual(scraper.referer, 'http://jsggzy.jszwfw.gov.cn/')
        # 关键差异：CATEGORY_NUM 前缀 003 而非 002
        self.assertEqual(scraper.CATEGORY_NUM, '003001001')
        # 关键差异：TIME_FIELD 为 infodatepx 而非 webdate
        self.assertEqual(scraper.TIME_FIELD, 'infodatepx')
        self.assertEqual(len(scraper.REGIONS), 13)

    def test_keywords_loaded(self):
        """验证关键词已加载。"""
        from scraper.ggzyjy_js import JsGgzyjyScraper
        scraper = JsGgzyjyScraper()
        self.assertTrue(len(scraper.keywords) > 0)
        self.assertIn('管道', scraper.keywords)


class TestJsRegions(unittest.TestCase):
    """验证江苏地区码配置。"""

    def test_regions_count(self):
        """验证包含 13 个地市。"""
        from scraper.ggzyjy_js.regions import REGIONS
        self.assertEqual(len(REGIONS), 13)

    def test_known_cities(self):
        """验证已知城市编码。"""
        from scraper.ggzyjy_js.regions import REGIONS
        self.assertEqual(REGIONS['320101']['name'], '南京市')
        self.assertEqual(REGIONS['320501']['name'], '苏州市')
        self.assertEqual(REGIONS['321301']['name'], '宿迁市')

    def test_all_codes_start_with_32(self):
        """验证所有地区码以 32 开头。"""
        from scraper.ggzyjy_js.regions import REGIONS
        for code in REGIONS:
            self.assertTrue(code.startswith('32'), f'{code} 应以 32 开头')


class TestRegistryHasGgzyjyJs(unittest.TestCase):
    """验证 registry 注册。"""

    def test_registry_entry(self):
        """验证 SCRAPER_REGISTRY 包含 ggzyjy_js 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('ggzyjy_js', SCRAPER_REGISTRY)
        entry = SCRAPER_REGISTRY['ggzyjy_js']
        self.assertEqual(entry['label'], '江苏公共资源交易')
        self.assertEqual(entry['import_path'], 'scraper.ggzyjy_js')
        self.assertEqual(entry['class_name'], 'JsGgzyjyScraper')
        self.assertTrue(entry['include_in_all'])
        self.assertTrue(entry['is_lead_source'])

    def test_dynamic_import(self):
        """验证通过 registry 动态加载无 ImportError。"""
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('ggzyjy_js')
        self.assertIsNotNone(cls)
        from scraper.ggzyjy_js import JsGgzyjyScraper
        self.assertIs(cls, JsGgzyjyScraper)


if __name__ == '__main__':
    unittest.main()
