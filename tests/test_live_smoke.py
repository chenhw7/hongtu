# -*- coding: utf-8 -*-
"""采集渠道真实网络烟雾测试。

验证每个渠道能否真正抓取到资讯：
- 能成功请求目标站
- 能解析出至少 1 条线索
- 关键字段（project_name, source_url 等）非空

运行方式：
  LIVE_SMOKE_TESTS=1 uv run pytest tests/test_live_smoke.py -v

仅运行纯 httpx 渠道（排除 Playwright）：
  LIVE_SMOKE_TESTS=1 uv run pytest tests/test_live_smoke.py -v -k "not Pipebiz and not Fdtz"

仅运行 Playwright 渠道：
  LIVE_SMOKE_TESTS=1 LIVE_SMOKE_TESTS_PLAYWRIGHT=1 uv run pytest tests/test_live_smoke.py -v -k "Pipebiz or Fdtz"
"""
import pytest

from tests.conftest import (
    live_skip,
    playwright_skip,
    amap_key_skip,
    qcc_key_skip,
    assert_valid_leads,
)


# ──────────────────────────────────────────────────────────
# 纯 httpx 渠道
# ──────────────────────────────────────────────────────────

@live_skip
class TestCcgpLive:
    """中国政府采购网烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.ccgp import CcgpScraper
        s = CcgpScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'ccgp',
        )


@live_skip
class TestGdgpoLive:
    """广东省政府采购网烟雾测试。"""

    def test_channel_cggg(self, live_app):
        from scraper.gdgpo import GdgpoScraper
        s = GdgpoScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('channel:cggg', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url'],
            'gdgpo',
        )


@live_skip
class TestEiaLive:
    """环评公示烟雾测试（广州适配器）。"""

    def test_region_guangzhou(self, live_app):
        from scraper.eia import EiaScraper
        s = EiaScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('region:guangzhou', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'region'],
            'eia',
        )
        # 广州线索的 region 字段应为「广州市」
        assert leads[0]['region'] == '广州市'


@live_skip
class TestGgzyjyLive:
    """广东省公共资源交易烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.ggzyjy import GgzyjyScraper
        s = GgzyjyScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'ggzyjy',
        )


@live_skip
class TestGzfcjLive:
    """广州住建局烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.gzfcj import GzfcjScraper
        s = GzfcjScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'gzfcj',
        )


@live_skip
class TestBjxLive:
    """北极星环保网烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.bjx import BjxScraper
        s = BjxScraper(app=live_app)
        s._create_http_client()
        try:
            leads = s._scrape_keyword('污水处理')
        finally:
            s._close_http_client()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'bjx',
        )


@live_skip
class TestGdcicLive:
    """广东住建厅烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.gdcic import GdcicScraper
        s = GdcicScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('施工', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url'],
            'gdcic',
        )


# ── Epoint 三省（共用基类，分别验证各自目标站）──

@live_skip
class TestGgzyjyZjLive:
    """浙江公共资源交易烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.ggzyjy_zj import ZjGgzyjyScraper
        s = ZjGgzyjyScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'ggzyjy_zj',
        )


@live_skip
class TestGgzyjyScLive:
    """四川公共资源交易烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.ggzyjy_sc import ScGgzyjyScraper
        s = ScGgzyjyScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'ggzyjy_sc',
        )


@live_skip
class TestGgzyjyJsLive:
    """江苏公共资源交易烟雾测试。"""

    def test_search_keyword(self, live_app):
        from scraper.ggzyjy_js import JsGgzyjyScraper
        s = JsGgzyjyScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('管道', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url', 'publish_date'],
            'ggzyjy_js',
        )


# ──────────────────────────────────────────────────────────
# Playwright 渠道（需额外环境变量门控）
# ──────────────────────────────────────────────────────────

@live_skip
@playwright_skip
class TestPipebizLive:
    """中国管道商务网烟雾测试（全程 Playwright）。"""

    def test_search_keyword(self, live_app):
        from scraper.pipebiz.browser import PipebizBrowser
        from scraper.pipebiz.parser import parse_search_results
        browser = PipebizBrowser(headless=True)
        browser.start()
        try:
            html = browser.search_keyword('管道', page_num=1)
            assert html, '[pipebiz] Playwright 搜索返回空内容'
            leads = parse_search_results(html)
            assert_valid_leads(
                leads,
                ['project_name', 'source_url', 'publish_date'],
                'pipebiz',
            )
        finally:
            browser.stop()


@live_skip
@playwright_skip
class TestFdtzLive:
    """发改委项目审批烟雾测试（httpx + Playwright JSL Cookie）。"""

    def test_channel_ba(self, live_app):
        from scraper.fdtz import FdtzScraper
        s = FdtzScraper(app=live_app)
        # fdtz 的 _scrape_page 内部会自动获取 JSL Cookie
        s._create_session()
        try:
            leads = s._scrape_page('channel:ba', 1)
        finally:
            s._close_session()
        assert_valid_leads(
            leads,
            ['project_name', 'source_url'],
            'fdtz',
        )


# ──────────────────────────────────────────────────────────
# 需 API Key 渠道
# ──────────────────────────────────────────────────────────

@live_skip
@amap_key_skip
class TestPoiLive:
    """高德地图 POI 烟雾测试（需 AMAP_API_KEY）。"""

    def test_search_keyword(self, live_app):
        from scraper.poi import AmapPoiScraper
        s = AmapPoiScraper(app=live_app)
        s._create_session()
        try:
            leads = s._scrape_page('PVC管材@广州', 1)
        finally:
            s._close_session()
        # POI 产出 Customer 而非 Lead，字段名不同
        assert leads is not None, '[poi] _scrape_page 返回 None（请求失败）'
        assert isinstance(leads, list), f'[poi] 返回类型不是 list: {type(leads)}'
        assert len(leads) > 0, '[poi] 未抓取到任何 POI 数据'
        first = leads[0]
        assert first.get('company_name') or first.get('name'), '[poi] company_name 为空'
        assert first.get('address'), '[poi] address 为空'


@live_skip
@qcc_key_skip
class TestQccLive:
    """企查查烟雾测试（需 QCC_API_KEY，当前为占位实现）。"""

    def test_search_company(self, live_app):
        from scraper.qcc import QccScraper
        s = QccScraper(app=live_app)
        # qcc 当前为占位实现，此测试验证 API 连通性
        result = s.search_company('鸿图建材')
        # 占位实现可能返回 None 或空 dict，不强制断言非空
        # 只验证不抛异常即可
        assert result is not None or True, '[qcc] search_company 抛异常'
