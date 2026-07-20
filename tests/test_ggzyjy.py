# -*- coding: utf-8 -*-
"""ggzyjy 采集模块单元测试。"""
import unittest
from datetime import date


class TestRegionsConfig(unittest.TestCase):
    """验证 regions.py 配置完整性。"""

    def test_regions_config(self):
        """验证 21 个地级市全部注册且 siteCode 格式正确。"""
        from scraper.ggzyjy.regions import REGIONS, PROVINCE_SITE_CODE

        self.assertEqual(len(REGIONS), 21, '应包含 21 个地级市')
        self.assertEqual(PROVINCE_SITE_CODE, '440000')

        # 验证关键字段
        expected_cities = [
            'guangzhou', 'shenzhen', 'zhuhai', 'shantou', 'foshan',
            'shaoguan', 'heyuan', 'meizhou', 'huizhou', 'shanwei',
            'dongguan', 'zhongshan', 'jiangmen', 'yangjiang', 'zhanjiang',
            'maoming', 'zhaoqing', 'qingyuan', 'chaozhou', 'jieyang', 'yunfu',
        ]
        for city_key in expected_cities:
            self.assertIn(city_key, REGIONS, f'缺少城市: {city_key}')
            region = REGIONS[city_key]
            self.assertIn('name', region)
            self.assertIn('siteCode', region)
            self.assertTrue(region['siteCode'].startswith('44'),
                            f'{city_key} siteCode 应以 44 开头')

    def test_specific_site_codes(self):
        """验证部分已知的 siteCode 编码正确。"""
        from scraper.ggzyjy.regions import REGIONS
        self.assertEqual(REGIONS['guangzhou']['siteCode'], '440100')
        self.assertEqual(REGIONS['shenzhen']['siteCode'], '440300')
        self.assertEqual(REGIONS['jiangmen']['siteCode'], '440700')
        self.assertEqual(REGIONS['dongguan']['siteCode'], '441900')


class TestParseItem(unittest.TestCase):
    """验证 parser.parse_item() 字段映射。"""

    def test_parse_item_basic(self):
        """验证基本字段映射。"""
        from scraper.ggzyjy.parser import parse_item

        mock_item = {
            'noticeId': 'f970e58a-1234-5678',
            'noticeTitle': '广州市某燃气管道拆除迁改工程施工总承包',
            'noticeSecondType': 'A',
            'noticeThirdType': 'A02',
            'noticeThirdTypeDesc': '中标结果',
            'projectTypeName': '市政',
            'regionName': '广州市',
            'projectOwner': '广州市政园建设管理有限公司',
            'projectCode': 'E4401002701503104001',
            'publishDate': '20260716190934',
            'tradingProcess': '3C31',
        }

        lead = parse_item(mock_item)

        self.assertEqual(lead['project_name'], '广州市某燃气管道拆除迁改工程施工总承包')
        self.assertEqual(lead['bidding_number'], 'E4401002701503104001')
        self.assertEqual(lead['announcement_type'], '中标结果')
        self.assertEqual(lead['buyer_name'], '广州市政园建设管理有限公司')
        self.assertEqual(lead['region'], '广州市')
        self.assertEqual(lead['publish_date'], date(2026, 7, 16))
        self.assertEqual(lead['publish_time'], '19:09')
        self.assertIn('source_url', lead)
        # 验证新 hash 路由 URL 格式
        self.assertIn('/#/44/new/jygg/v3/A', lead['source_url'])
        self.assertIn('noticeId=f970e58a', lead['source_url'])
        self.assertIn('bizCode=3C31', lead['source_url'])
        self.assertIn('titleDetails=工程建设', lead['source_url'])
        self.assertIn('classify=A02', lead['source_url'])

    def test_parse_item_empty_fields(self):
        """验证空字段不会出现在结果中。"""
        from scraper.ggzyjy.parser import parse_item

        mock_item = {
            'noticeId': 'abc-123',
            'noticeTitle': '测试项目',
            'noticeSecondType': 'A',
            'publishDate': '',
            'regionName': '',
            'projectOwner': '',
            'projectCode': '',
        }

        lead = parse_item(mock_item)
        self.assertEqual(lead['project_name'], '测试项目')
        # 空字段应被过滤
        self.assertNotIn('region', lead)
        self.assertNotIn('buyer_name', lead)

    def test_parse_item_url_with_trading_process(self):
        """验证带 tradingProcess 的 URL 构建。"""
        from scraper.ggzyjy.parser import parse_item

        mock_item = {
            'noticeId': '5c0fe74d-780b-4c69-81b5-28dd94fb2f0c-3C31',
            'noticeTitle': '某工程施工招标',
            'noticeSecondType': 'A',
            'noticeThirdType': 'A01',
            'noticeThirdTypeDesc': '招标公告',
            'projectCode': 'E4401001123002549001',
            'publishDate': '20260715090000',
            'siteCode': '440900',
            'tradingProcess': '3C31',
            'regionName': '茂名市',
            'projectOwner': '某建设单位',
        }

        lead = parse_item(mock_item)
        self.assertIn('bizCode=3C31', lead['source_url'])
        self.assertIn('siteCode=440900', lead['source_url'])
        self.assertIn('publishDate=20260715090000', lead['source_url'])
        self.assertIn('classify=A01', lead['source_url'])
        self.assertIn('/#/44/new/jygg/v3/A', lead['source_url'])

    def test_parse_item_url_government_purchase(self):
        """验证政府采购类型的 URL 构建。"""
        from scraper.ggzyjy.parser import parse_item

        mock_item = {
            'noticeId': 'abcd-1234-5678-9999',
            'noticeTitle': '某政府采购项目',
            'noticeSecondType': 'D',
            'noticeThirdType': 'D01',
            'noticeThirdTypeDesc': '采购公告',
            'projectCode': 'D4401001234567890001',
            'publishDate': '20260718100000',
            'siteCode': '440100',
            'tradingProcess': '',
            'regionName': '广州市',
            'projectOwner': '某政府单位',
        }

        lead = parse_item(mock_item)
        # 路径包含 /v3/D
        self.assertIn('/#/44/new/jygg/v3/D', lead['source_url'])
        # titleDetails=政府采购
        self.assertIn('titleDetails=政府采购', lead['source_url'])
        # tradingProcess 为空，bizCode 应取 noticeId 前4位
        self.assertIn('bizCode=abcd', lead['source_url'])
        self.assertIn('classify=D01', lead['source_url'])


class TestParseGgzyjyDate(unittest.TestCase):
    """验证日期解析。"""

    def test_full_format(self):
        """验证完整的 yyyyMMddHHmmss 格式。"""
        from scraper.ggzyjy.utils import parse_ggzyjy_date
        d, t = parse_ggzyjy_date('20260716190934')
        self.assertEqual(d, date(2026, 7, 16))
        self.assertEqual(t, '19:09')

    def test_date_only(self):
        """验证仅日期部分（8位）。"""
        from scraper.ggzyjy.utils import parse_ggzyjy_date
        d, t = parse_ggzyjy_date('20260716')
        self.assertEqual(d, date(2026, 7, 16))
        self.assertIsNone(t)

    def test_empty_input(self):
        """验证空输入返回 None。"""
        from scraper.ggzyjy.utils import parse_ggzyjy_date
        d, t = parse_ggzyjy_date('')
        self.assertIsNone(d)
        self.assertIsNone(t)

    def test_invalid_input(self):
        """验证无效输入返回 None。"""
        from scraper.ggzyjy.utils import parse_ggzyjy_date
        d, t = parse_ggzyjy_date('not-a-date')
        self.assertIsNone(d)
        self.assertIsNone(t)


class TestParseBudget(unittest.TestCase):
    """验证金额解析。"""

    def test_wan_yuan(self):
        """验证万元单位。"""
        from scraper.ggzyjy.utils import parse_budget
        self.assertEqual(parse_budget('最高投标限价：387.5万元'), 3875000.0)

    def test_yuan(self):
        """验证元单位。"""
        from scraper.ggzyjy.utils import parse_budget
        self.assertAlmostEqual(parse_budget('预算金额 1234567.89 元'), 1234567.89)

    def test_yi_yuan(self):
        """验证亿元单位。"""
        from scraper.ggzyjy.utils import parse_budget
        self.assertEqual(parse_budget('合同估算价 1.5亿元'), 150000000.0)

    def test_comma_number(self):
        """验证千分位逗号。"""
        from scraper.ggzyjy.utils import parse_budget
        self.assertEqual(parse_budget('金额 1,234.56 元'), 1234.56)

    def test_no_match(self):
        """验证无匹配返回 None。"""
        from scraper.ggzyjy.utils import parse_budget
        self.assertIsNone(parse_budget('无金额信息'))
        self.assertIsNone(parse_budget(''))
        self.assertIsNone(parse_budget(None))


class TestParseRichtextFields(unittest.TestCase):
    """验证 richText HTML 解析。"""

    def test_table_extraction(self):
        """验证从 HTML 表格中提取键值对。"""
        from scraper.ggzyjy.utils import parse_richtext_fields

        html = '''
        <table>
            <tr><td>招标人</td><td>广州市某建设公司</td></tr>
            <tr><td>联系人</td><td>张三</td></tr>
            <tr><td>联系电话</td><td>020-12345678</td></tr>
        </table>
        '''
        fields = parse_richtext_fields(html)
        self.assertEqual(fields['招标人'], '广州市某建设公司')
        self.assertEqual(fields['联系人'], '张三')
        self.assertEqual(fields['联系电话'], '020-12345678')

    def test_text_label_extraction(self):
        """验证从纯文本标签:值形式中提取。"""
        from scraper.ggzyjy.utils import parse_richtext_fields

        html = '<div><p>招标人：深圳市某工程公司</p><p>预算金额：500万元</p></div>'
        fields = parse_richtext_fields(html)
        self.assertEqual(fields['招标人'], '深圳市某工程公司')
        self.assertEqual(fields['预算金额'], '500万元')

    def test_empty_input(self):
        """验证空输入返回空 dict。"""
        from scraper.ggzyjy.utils import parse_richtext_fields
        self.assertEqual(parse_richtext_fields(''), {})
        self.assertEqual(parse_richtext_fields(None), {})


class TestRegistryHasGgzyjy(unittest.TestCase):
    """验证 registry 中包含 ggzyjy。"""

    def test_registry_has_ggzyjy(self):
        """验证 SCRAPER_REGISTRY 中包含 ggzyjy 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('ggzyjy', SCRAPER_REGISTRY)
        entry = SCRAPER_REGISTRY['ggzyjy']
        self.assertEqual(entry['label'], '公共资源交易')
        self.assertEqual(entry['import_path'], 'scraper.ggzyjy')
        self.assertEqual(entry['class_name'], 'GgzyjyScraper')
        self.assertTrue(entry['include_in_all'])
        self.assertTrue(entry['is_lead_source'])

    def test_get_source_label(self):
        """验证 get_source_label 返回正确标签。"""
        from scraper.registry import get_source_label
        self.assertEqual(get_source_label('ggzyjy'), '公共资源交易')

    def test_get_source_badge_class(self):
        """验证 badge 样式类。"""
        from scraper.registry import get_source_badge_class
        self.assertEqual(get_source_badge_class('ggzyjy'), 'badge-teal')


class TestScraperClassImport(unittest.TestCase):
    """验证能正常 import GgzyjyScraper。"""

    def test_import_class(self):
        """验证 GgzyjyScraper 类可以正常导入。"""
        from scraper.ggzyjy import GgzyjyScraper
        self.assertEqual(GgzyjyScraper.source_type, 'ggzyjy')
        self.assertEqual(GgzyjyScraper.base_url, 'https://ygp.gdzwfw.gov.cn')

    def test_instantiate(self):
        """验证可以正常实例化。"""
        from scraper.ggzyjy import GgzyjyScraper
        scraper = GgzyjyScraper()
        self.assertIsNotNone(scraper)
        self.assertIsNotNone(scraper.ggzyjy_keywords)

    def test_default_keywords(self):
        """验证默认关键词包含搜索词和频道伪关键词。"""
        from scraper.ggzyjy import GgzyjyScraper
        scraper = GgzyjyScraper()
        keywords = scraper.default_keywords()
        self.assertIn('channel:jsgc', keywords)
        self.assertIn('channel:zfcg', keywords)
        # 应包含管道等搜索关键词
        self.assertIn('管道', keywords)

    def test_keyword_display(self):
        """验证关键词显示名称转换。"""
        from scraper.ggzyjy import GgzyjyScraper
        scraper = GgzyjyScraper()
        self.assertEqual(scraper._keyword_display('channel:jsgc'), '工程建设（全省）')
        self.assertEqual(scraper._keyword_display('channel:zfcg'), '政府采购（全省）')
        self.assertEqual(scraper._keyword_display('channel:jsgc:guangzhou'), '工程建设·广州市')
        self.assertEqual(scraper._keyword_display('管道'), '管道')

    def test_registry_dynamic_import(self):
        """验证通过 registry 动态加载可以正常获取类。"""
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('ggzyjy')
        self.assertIsNotNone(cls)
        from scraper.ggzyjy import GgzyjyScraper
        self.assertIs(cls, GgzyjyScraper)


class TestParsePhone(unittest.TestCase):
    """验证电话号码解析。"""

    def test_mobile(self):
        from scraper.ggzyjy.utils import parse_phone
        self.assertEqual(parse_phone('联系人电话 13812345678'), '13812345678')

    def test_landline(self):
        from scraper.ggzyjy.utils import parse_phone
        self.assertEqual(parse_phone('电话：020-12345678'), '020-12345678')

    def test_empty(self):
        from scraper.ggzyjy.utils import parse_phone
        self.assertIsNone(parse_phone(''))
        self.assertIsNone(parse_phone(None))


if __name__ == '__main__':
    unittest.main()
