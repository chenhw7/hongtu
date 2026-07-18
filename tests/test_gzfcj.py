# -*- coding: utf-8 -*-
"""gzfcj 采集模块单元测试。"""
import unittest
from datetime import date


class TestParsePermitItem(unittest.TestCase):
    """验证 parser.parse_permit_item() 字段映射。"""

    def test_parse_permit_basic(self):
        """验证施工许可证基本字段映射。"""
        from scraper.gzfcj.parser import parse_permit_item

        mock_item = {
            'gcmc': '广州市增城区荔湖街新城大道东侧18005200A24018号地块建设项目',
            'jsdd': '广州市增城区荔湖街新城大道东侧',
            'jsdw': '广州市增城区城苑投资发展有限公司',
            'sgdw': '广州协安建设工程有限公司',
            'jldw': '广东省建筑工程监理有限公司',
            'sgxkzh': '440118202607170201',
            'pzrq': '2026/7/17 0:00:00',
            'sgxkzt': '有效',
        }

        lead = parse_permit_item(mock_item)

        self.assertEqual(lead['project_name'], '广州市增城区荔湖街新城大道东侧18005200A24018号地块建设项目')
        self.assertEqual(lead['buyer_address'], '广州市增城区荔湖街新城大道东侧')
        self.assertEqual(lead['buyer_name'], '广州市增城区城苑投资发展有限公司')
        self.assertEqual(lead['agency_name'], '广州协安建设工程有限公司')
        self.assertEqual(lead['bidding_number'], '440118202607170201')
        self.assertEqual(lead['announcement_type'], '施工许可证')
        self.assertEqual(lead['region'], '广州市')
        self.assertEqual(lead['publish_date'], date(2026, 7, 17))
        self.assertIn('source_url', lead)
        # 状态和监理单位
        self.assertEqual(lead['sgxkzt'], '有效')
        self.assertEqual(lead['jldw'], '广东省建筑工程监理有限公司')

    def test_parse_permit_null_fields(self):
        """验证施工许可证 null 字段（如监理单位为 null）不影响解析。"""
        from scraper.gzfcj.parser import parse_permit_item

        mock_item = {
            'gcmc': '某室内装饰项目',
            'jsdd': '广州市天河区',
            'jsdw': '广州某公司',
            'sgdw': '湖南某装饰公司',
            'jldw': None,
            'sgxkzh': '440106202607170199',
            'pzrq': '2026/7/17 0:00:00',
            'sgxkzt': '有效',
        }

        lead = parse_permit_item(mock_item)
        self.assertEqual(lead['project_name'], '某室内装饰项目')
        # jldw 为 None，不应出现在结果中
        self.assertNotIn('jldw', lead)

    def test_parse_permit_empty_fields_filtered(self):
        """验证空字段不会出现在结果中。"""
        from scraper.gzfcj.parser import parse_permit_item

        mock_item = {
            'gcmc': '测试项目',
            'jsdd': '',
            'jsdw': '',
            'sgdw': '',
            'jldw': '',
            'sgxkzh': '',
            'pzrq': '',
            'sgxkzt': '',
        }

        lead = parse_permit_item(mock_item)
        self.assertEqual(lead['project_name'], '测试项目')
        self.assertNotIn('buyer_address', lead)
        self.assertNotIn('buyer_name', lead)
        self.assertNotIn('agency_name', lead)
        self.assertNotIn('bidding_number', lead)
        self.assertNotIn('publish_date', lead)


class TestParseAcceptanceItem(unittest.TestCase):
    """验证 parser.parse_acceptance_item() 字段映射。"""

    def test_parse_acceptance_basic(self):
        """验证竣工验收备案基本字段映射。"""
        from scraper.gzfcj.parser import parse_acceptance_item

        mock_item = {
            'pegcmc': '天河外国语学校智慧城校区建设工程（建筑工程）-北校区',
            'babh': '穗(天)建验备2026-075',
            'pejsdd': '广州市天河区长兴街道',
            'jsdw': '广州市天河区教育局',
            'sgdw': '中国建筑第八工程局有限公司',
            'spbm': '天河区住房建设和园林局',
            'peblrq': '2026/7/17 18:40:46',
            'yjsbh': '穗联验(天)字〔2026〕075号',
        }

        lead = parse_acceptance_item(mock_item)

        self.assertEqual(lead['project_name'], '天河外国语学校智慧城校区建设工程（建筑工程）-北校区')
        self.assertEqual(lead['buyer_address'], '广州市天河区长兴街道')
        self.assertEqual(lead['buyer_name'], '广州市天河区教育局')
        self.assertEqual(lead['agency_name'], '中国建筑第八工程局有限公司')
        self.assertEqual(lead['bidding_number'], '穗(天)建验备2026-075')
        self.assertEqual(lead['announcement_type'], '竣工验收备案')
        self.assertEqual(lead['region'], '广州市')
        self.assertEqual(lead['publish_date'], date(2026, 7, 17))
        self.assertIn('source_url', lead)
        # 审批部门和联合验收编号
        self.assertEqual(lead['spbm'], '天河区住房建设和园林局')
        self.assertEqual(lead['yjsbh'], '穗联验(天)字〔2026〕075号')

    def test_parse_acceptance_empty_fields_filtered(self):
        """验证竣工验收空字段被过滤。"""
        from scraper.gzfcj.parser import parse_acceptance_item

        mock_item = {
            'pegcmc': '测试竣工项目',
            'babh': '',
            'pejsdd': '',
            'jsdw': '',
            'sgdw': '',
            'spbm': '',
            'peblrq': '',
            'yjsbh': '',
        }

        lead = parse_acceptance_item(mock_item)
        self.assertEqual(lead['project_name'], '测试竣工项目')
        self.assertNotIn('buyer_address', lead)
        self.assertNotIn('buyer_name', lead)
        self.assertNotIn('publish_date', lead)


class TestParseDate(unittest.TestCase):
    """验证日期解析。"""

    def test_full_format(self):
        """验证完整日期格式 'yyyy/M/d H:mm:ss'。"""
        from scraper.gzfcj.parser import _parse_date
        self.assertEqual(_parse_date('2026/7/17 0:00:00'), date(2026, 7, 17))
        self.assertEqual(_parse_date('2026/7/17 18:40:46'), date(2026, 7, 17))

    def test_date_only(self):
        """验证仅日期格式。"""
        from scraper.gzfcj.parser import _parse_date
        self.assertEqual(_parse_date('2026/7/17'), date(2026, 7, 17))

    def test_empty_input(self):
        """验证空输入返回 None。"""
        from scraper.gzfcj.parser import _parse_date
        self.assertIsNone(_parse_date(''))
        self.assertIsNone(_parse_date(None))

    def test_invalid_input(self):
        """验证无效输入返回 None。"""
        from scraper.gzfcj.parser import _parse_date
        self.assertIsNone(_parse_date('not-a-date'))


class TestRegistryHasGzfcj(unittest.TestCase):
    """验证 registry 中包含 gzfcj。"""

    def test_registry_has_gzfcj(self):
        """验证 SCRAPER_REGISTRY 中包含 gzfcj 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('gzfcj', SCRAPER_REGISTRY)
        entry = SCRAPER_REGISTRY['gzfcj']
        self.assertEqual(entry['label'], '广州住建局')
        self.assertEqual(entry['import_path'], 'scraper.gzfcj')
        self.assertEqual(entry['class_name'], 'GzfcjScraper')
        self.assertEqual(entry['badge_class'], 'badge-cyan')
        self.assertTrue(entry['include_in_all'])
        self.assertTrue(entry['is_lead_source'])

    def test_get_source_label(self):
        """验证 get_source_label 返回正确标签。"""
        from scraper.registry import get_source_label
        self.assertEqual(get_source_label('gzfcj'), '广州住建局')

    def test_config_source_sites(self):
        """验证 config 中包含 gzfcj 官网地址。"""
        from app.config import Config
        self.assertIn('gzfcj', Config.SCRAPER_SOURCE_SITES)
        self.assertEqual(Config.SCRAPER_SOURCE_SITES['gzfcj'], 'https://zfcj.gz.gov.cn/')


class TestScraperClassImport(unittest.TestCase):
    """验证能正常 import GzfcjScraper。"""

    def test_import_class(self):
        """验证 GzfcjScraper 类可以正常导入。"""
        from scraper.gzfcj import GzfcjScraper
        self.assertEqual(GzfcjScraper.source_type, 'gzfcj')
        self.assertEqual(GzfcjScraper.base_url, 'https://zfcj.gz.gov.cn')

    def test_instantiate(self):
        """验证可以正常实例化。"""
        from scraper.gzfcj import GzfcjScraper
        scraper = GzfcjScraper()
        self.assertIsNotNone(scraper)
        self.assertIsNotNone(scraper.gzfcj_keywords)
        self.assertGreater(len(scraper.gzfcj_keywords), 0)

    def test_default_keywords(self):
        """验证默认关键词包含平台关键词。"""
        from scraper.gzfcj import GzfcjScraper
        scraper = GzfcjScraper()
        keywords = scraper.default_keywords()
        # 应包含管道等搜索关键词
        self.assertIn('管道', keywords)

    def test_registry_dynamic_import(self):
        """验证通过 registry 动态加载可以正常获取类。"""
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('gzfcj')
        self.assertIsNotNone(cls)
        from scraper.gzfcj import GzfcjScraper
        self.assertIs(cls, GzfcjScraper)


if __name__ == '__main__':
    unittest.main()
