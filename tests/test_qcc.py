# -*- coding: utf-8 -*-
"""企查查（qcc）采集模块单元测试。"""
import unittest
from datetime import date
from unittest.mock import MagicMock, patch


class TestQccScraperInit(unittest.TestCase):
    """验证 QccScraper 初始化行为。"""

    def test_init_without_app(self):
        """无 app 时使用默认值（api_key='', daily_limit=100）。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        self.assertEqual(scraper.api_key, '')
        self.assertEqual(scraper.daily_limit, 100)
        self.assertEqual(scraper.source_type, 'qcc')
        self.assertEqual(scraper.base_url, 'https://openapi.qcc.com')

    def test_init_with_app(self):
        """有 app 时从 config 读取 QCC_API_KEY 和 QCC_DAILY_LIMIT。"""
        from scraper.qcc import QccScraper
        app = MagicMock()
        app.config = {
            'QCC_API_KEY': 'test-key-123',
            'QCC_DAILY_LIMIT': 50,
            'SCRAPE_DELAY_MIN': 1,
            'SCRAPE_DELAY_MAX': 2,
            'SCRAPE_MAX_RETRIES': 2,
            'SCRAPER_KEYWORDS': [],
            'SCRAPE_CHECK_ROBOTS': False,
            'SCRAPE_ANTI_SCRAPE_WAIT': 0,
        }
        scraper = QccScraper(app=app)
        self.assertEqual(scraper.api_key, 'test-key-123')
        self.assertEqual(scraper.daily_limit, 50)

    def test_source_type_is_qcc(self):
        """source_type 属性必须为 'qcc'（与 registry 注册一致）。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        self.assertEqual(scraper.source_type, 'qcc')


class TestQccScraperRunWithoutKey(unittest.TestCase):
    """验证无 API Key 时的优雅退出行为。"""

    def test_run_without_api_key_returns_zero(self):
        """未配置 API Key 时 run() 直接返回 0，不报错。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        # 确保 api_key 为空
        self.assertEqual(scraper.api_key, '')
        result = scraper.run()
        self.assertEqual(result, 0)

    def test_run_with_empty_key_and_keywords(self):
        """即使传了 keywords，无 Key 时仍应优雅退出。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        result = scraper.run(keywords=['某公司'])
        self.assertEqual(result, 0)


class TestQccScraperDailyLimit(unittest.TestCase):
    """验证日限额控制逻辑。"""

    def test_daily_limit_triggers_stop(self):
        """当日已用次数达到限额时，不再发起 API 请求。"""
        from scraper.qcc import QccScraper

        app = MagicMock()
        app.config = {
            'QCC_API_KEY': 'test-key',
            'QCC_DAILY_LIMIT': 2,
            'SCRAPE_DELAY_MIN': 0,
            'SCRAPE_DELAY_MAX': 0,
            'SCRAPE_MAX_RETRIES': 1,
            'SCRAPER_KEYWORDS': [],
            'SCRAPE_CHECK_ROBOTS': False,
            'SCRAPE_ANTI_SCRAPE_WAIT': 0,
            'instance_path': '/tmp/test_instance',
        }
        app.instance_path = '/tmp/test_instance'

        scraper = QccScraper(app=app)
        # 模拟已达到日限额
        scraper._daily_used = 2
        scraper._daily_date = date.today()

        # Mock 掉 create_task 和 session 创建，避免真实 DB/网络调用
        scraper.create_task = MagicMock(return_value=MagicMock(id=1))
        scraper.update_task = MagicMock()
        scraper._progress_start = MagicMock()
        scraper._progress_finish = MagicMock()
        scraper._progress_update = MagicMock()
        scraper._progress_clear_control = MagicMock()
        scraper._create_session = MagicMock()
        scraper._close_session = MagicMock()
        scraper._check_pause_and_stop = MagicMock()

        # Mock _get_pending_companies 返回两个公司名
        scraper._get_pending_companies = MagicMock(return_value=['公司A', '公司B'])
        scraper._has_profile = MagicMock(return_value=False)
        scraper._query_company = MagicMock(return_value={'data': 'test'})
        scraper._save_profile = MagicMock(return_value=True)

        result = scraper.run(keywords=['公司A', '公司B'])

        # 日限额已到，不应调用 _query_company
        scraper._query_company.assert_not_called()
        self.assertEqual(result, 0)


class TestQccScraperRegistry(unittest.TestCase):
    """验证 qcc 在 registry 中正确注册。"""

    def test_registry_contains_qcc(self):
        """SCRAPER_REGISTRY 包含 qcc 条目。"""
        from scraper.registry import SCRAPER_REGISTRY
        self.assertIn('qcc', SCRAPER_REGISTRY)

    def test_registry_qcc_fields(self):
        """qcc 注册条目字段正确。"""
        from scraper.registry import SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['qcc']
        self.assertEqual(entry['label'], '企查查')
        self.assertEqual(entry['import_path'], 'scraper.qcc')
        self.assertEqual(entry['class_name'], 'QccScraper')
        self.assertEqual(entry['badge_class'], 'badge-purple')
        self.assertFalse(entry['include_in_all'])
        self.assertFalse(entry['is_lead_source'])
        self.assertEqual(entry['source_site'], 'https://openapi.qcc.com/')

    def test_qcc_not_in_all_sources(self):
        """qcc 不在 include_in_all 列表中（付费接口不参与全量采集）。"""
        from scraper.registry import get_all_source_types
        all_types = get_all_source_types(include_in_all=True)
        self.assertNotIn('qcc', all_types)

    def test_qcc_class_loadable(self):
        """get_scraper_class 能正确加载 QccScraper 类。"""
        from scraper.registry import get_scraper_class
        from scraper.qcc import QccScraper
        cls = get_scraper_class('qcc')
        self.assertIs(cls, QccScraper)


class TestQccConfig(unittest.TestCase):
    """验证 config.py 中 qcc 相关配置项。"""

    def test_qcc_api_key_default(self):
        """QCC_API_KEY 默认为空字符串。"""
        from app.config import Config
        self.assertEqual(Config.QCC_API_KEY, '')

    def test_qcc_daily_limit_default(self):
        """QCC_DAILY_LIMIT 默认为 100。"""
        from app.config import Config
        self.assertEqual(Config.QCC_DAILY_LIMIT, 100)

    def test_qcc_in_source_sites(self):
        """SCRAPER_SOURCE_SITES 包含 qcc 官网地址。"""
        from app.config import Config
        self.assertIn('qcc', Config.SCRAPER_SOURCE_SITES)
        self.assertEqual(Config.SCRAPER_SOURCE_SITES['qcc'], 'https://openapi.qcc.com/')


class TestQccApiMethods(unittest.TestCase):
    """验证 API 调用方法的框架行为（不发起真实网络请求）。"""

    def test_search_company_returns_none_on_failure(self):
        """_query_api 失败时 search_company 返回 None。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        scraper._query_api = MagicMock(return_value=None)
        result = scraper.search_company('测试公司')
        self.assertIsNone(result)

    def test_get_business_info_returns_none_on_failure(self):
        """_query_api 失败时 get_business_info 返回 None。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        scraper._query_api = MagicMock(return_value=None)
        result = scraper.get_business_info('测试公司')
        self.assertIsNone(result)

    def test_get_dishonest_info_returns_none_on_failure(self):
        """_query_api 失败时 get_dishonest_info 返回 None。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        scraper._query_api = MagicMock(return_value=None)
        result = scraper.get_dishonest_info('测试公司')
        self.assertIsNone(result)

    def test_query_company_returns_none_on_search_failure(self):
        """搜索失败时 _query_company 返回 None。"""
        from scraper.qcc import QccScraper
        scraper = QccScraper()
        scraper.search_company = MagicMock(return_value=None)
        result = scraper._query_company('测试公司')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
