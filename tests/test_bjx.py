# -*- coding: utf-8 -*-
"""bjx 采集模块单元测试。

仅测试纯函数解析逻辑，不测试真实 Playwright 页面操作（依赖网络/浏览器）。
"""
import pytest


# ------------------------------------------------------------------
# parser 测试
# ------------------------------------------------------------------

MOCK_LIST_HTML = """
<html><body>
<ul class="list">
    <li>
        <a href="/news/202607/t12345.html">XX市污水处理厂提标改造工程招标公告</a>
        <span class="date">2026-07-15</span>
        <span class="type">招标公告</span>
    </li>
    <li>
        <a href="/news/202607/t12346.html">YY县生活垃圾焚烧发电项目环评公示</a>
        <span class="date">2026-07-14</span>
        <span class="type">中标公告</span>
    </li>
    <li>
        <a href="https://huanbao.bjx.com.cn/news/202607/t12347.html">ZZ工业园区烟气脱硫改造工程</a>
        <span class="date">2026/07/13</span>
    </li>
</ul>
</body></html>
"""


class TestParseListPage:
    """测试列表页解析。"""

    def test_parser_list_page(self):
        from scraper.bjx.parser import parse_list_page
        results = parse_list_page(MOCK_LIST_HTML)
        assert len(results) == 3

        # 第 1 条
        assert results[0]['project_name'] == 'XX市污水处理厂提标改造工程招标公告'
        assert '/news/202607/t12345.html' in results[0]['source_url']
        assert results[0]['publish_date'] == '2026-07-15'
        assert results[0]['announcement_type'] == '招标公告'

        # 第 2 条
        assert '垃圾焚烧' in results[1]['project_name']
        assert results[1]['publish_date'] == '2026-07-14'
        assert results[1]['announcement_type'] == '中标公告'

        # 第 3 条 — 绝对 URL
        assert results[2]['source_url'] == 'https://huanbao.bjx.com.cn/news/202607/t12347.html'
        assert results[2]['publish_date'] == '2026-07-13'

    def test_parser_list_page_empty(self):
        from scraper.bjx.parser import parse_list_page
        assert parse_list_page('') == []
        assert parse_list_page(None) == []
        assert parse_list_page('<html><body></body></html>') == []

    def test_parser_list_page_table(self):
        from scraper.bjx.parser import parse_list_page
        html = """
        <html><body>
        <table>
        <tbody>
            <tr>
                <td><a href="/detail/100.html">污水处理设备采购项目招标</a></td>
                <td>2026-06-20</td>
            </tr>
            <tr>
                <td><a href="/detail/101.html">固废处理设施建设工程</a></td>
                <td>2026-06-19</td>
            </tr>
        </tbody>
        </table>
        </body></html>
        """
        results = parse_list_page(html)
        assert len(results) == 2
        assert '污水处理' in results[0]['project_name']
        assert results[0]['publish_date'] == '2026-06-20'


MOCK_DETAIL_HTML = """
<html><body>
<div class="content">
    <h1>XX市污水处理厂提标改造工程招标公告</h1>
    <p>招标编号：BJX-2026-001</p>
    <p>采购人：XX市排水有限公司</p>
    <p>联系人：李四</p>
    <p>联系电话：0755-87654321</p>
    <p>预算金额：800万元</p>
    <p>项目地区：广东省深圳市</p>
    <p>代理机构：深圳市环保招标有限公司</p>
    <p>投标截止时间：2026-08-01 09:00</p>
    <div class="attachment">
        <a href="/files/招标文件.pdf">招标文件.pdf</a>
        <a href="/files/技术要求.docx">技术要求.docx</a>
    </div>
</div>
</body></html>
"""


class TestParseDetailPage:
    """测试详情页解析。"""

    def test_parser_detail_page(self):
        from scraper.bjx.parser import parse_detail_page
        result = parse_detail_page(MOCK_DETAIL_HTML)

        assert result.get('buyer_name') == 'XX市排水有限公司'
        assert result.get('contact_person') == '李四'
        assert result.get('phone') == '0755-87654321'
        assert '800' in result.get('budget_amount', '')
        assert '深圳' in result.get('region', '')
        assert result.get('bidding_number') == 'BJX-2026-001'
        assert '深圳' in result.get('agency_name', '')

    def test_parser_detail_page_attachments(self):
        from scraper.bjx.parser import parse_detail_page
        result = parse_detail_page(MOCK_DETAIL_HTML)

        attachments = result.get('attachments', [])
        assert len(attachments) >= 1
        urls = [a['url'] for a in attachments]
        assert any('招标文件' in u or 'pdf' in u for u in urls)

    def test_parser_detail_page_empty(self):
        from scraper.bjx.parser import parse_detail_page
        assert parse_detail_page('') == {}
        assert parse_detail_page(None) == {}


# ------------------------------------------------------------------
# utils 测试
# ------------------------------------------------------------------

class TestCleanBjxText:
    """测试文本清理函数。"""

    def test_clean_bjx_text(self):
        from scraper.bjx.utils import clean_bjx_text

        assert clean_bjx_text('') == ''
        assert clean_bjx_text(None) == ''
        assert clean_bjx_text('  hello  world  ') == 'hello world'
        assert clean_bjx_text('test&nbsp;text') == 'test text'
        assert clean_bjx_text('<b>bold</b> text') == 'bold text'
        assert clean_bjx_text('line1\n  line2\t  line3') == 'line1 line2 line3'


class TestParseBjxDate:
    """测试日期解析函数。"""

    def test_parse_bjx_date(self):
        from scraper.bjx.utils import parse_bjx_date

        # 标准格式
        assert parse_bjx_date('2026-07-16') == ('2026-07-16', '')
        assert parse_bjx_date('2026/07/16') == ('2026-07-16', '')
        assert parse_bjx_date('2026.07.16') == ('2026-07-16', '')
        assert parse_bjx_date('2026年07月16日') == ('2026-07-16', '')

        # 带时间
        assert parse_bjx_date('2026-07-16 10:30:00') == ('2026-07-16', '10:30:00')
        assert parse_bjx_date('2026-07-16 10:30') == ('2026-07-16', '10:30:00')

        # 空值
        assert parse_bjx_date('') == ('', '')
        assert parse_bjx_date(None) == ('', '')
        assert parse_bjx_date('invalid') == ('', '')


class TestIsWafChallengePage:
    """测试 WAF 拦截检测。"""

    def test_waf_challenge_detected(self):
        from scraper.bjx.utils import is_waf_challenge_page

        # WAF 特征
        waf_html = '<html><body><script>var arg1="abc123";setTimeout(function(){eval(...)},1000)</script></body></html>'
        assert is_waf_challenge_page(waf_html) is True

    def test_normal_page(self):
        from scraper.bjx.utils import is_waf_challenge_page

        normal_html = '<html><body><ul class="list"><li>正常内容</li></ul></body></html>'
        assert is_waf_challenge_page(normal_html) is False

    def test_empty_page(self):
        from scraper.bjx.utils import is_waf_challenge_page
        assert is_waf_challenge_page('') is False
        assert is_waf_challenge_page(None) is False


class TestShouldRefreshCookies:
    """测试 Cookie 刷新判断。"""

    def test_refresh_empty_cookies(self):
        from scraper.bjx.utils import should_refresh_cookies
        import time

        # 空 Cookie 始终需要刷新
        assert should_refresh_cookies(time.time(), '') is True

    def test_refresh_expired(self):
        from scraper.bjx.utils import should_refresh_cookies
        import time

        # 过期 Cookie（超过 300 秒）
        old_time = time.time() - 400
        assert should_refresh_cookies(old_time, 'abc=123') is True

    def test_no_refresh_valid(self):
        from scraper.bjx.utils import should_refresh_cookies
        import time

        # 有效 Cookie
        recent_time = time.time() - 100
        assert should_refresh_cookies(recent_time, 'abc=123') is False


# ------------------------------------------------------------------
# registry 测试
# ------------------------------------------------------------------

class TestRegistry:
    """测试 registry 注册。"""

    def test_registry_has_bjx(self):
        from scraper.registry import SCRAPER_REGISTRY
        assert 'bjx' in SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['bjx']
        assert entry['label'] == '北极星环保网'
        assert entry['class_name'] == 'BjxScraper'
        assert entry['badge_class'] == 'badge-green'
        assert entry['include_in_all'] is True
        assert entry['is_lead_source'] is True
        assert 'bjx.com.cn' in entry['source_site']

    def test_scraper_class_import(self):
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('bjx')
        assert cls is not None
        assert cls.__name__ == 'BjxScraper'

    def test_scraper_source_type(self):
        from scraper.bjx import BjxScraper
        assert BjxScraper.source_type == 'bjx'
        assert 'bjx.com.cn' in BjxScraper.base_url


# ------------------------------------------------------------------
# keywords 测试
# ------------------------------------------------------------------

class TestKeywords:
    """测试关键词配置。"""

    def test_bjx_keywords_exist(self):
        from scraper.keywords import BJX_KEYWORDS_FINAL
        assert len(BJX_KEYWORDS_FINAL) > 0
        assert any('污水' in kw for kw in BJX_KEYWORDS_FINAL)
        assert any('环保' in kw for kw in BJX_KEYWORDS_FINAL)


# ------------------------------------------------------------------
# config 测试
# ------------------------------------------------------------------

class TestConfig:
    """测试配置文件。"""

    def test_config_source_sites_has_bjx(self):
        from app.config import Config
        assert 'bjx' in Config.SCRAPER_SOURCE_SITES
        assert 'bjx.com.cn' in Config.SCRAPER_SOURCE_SITES['bjx']
