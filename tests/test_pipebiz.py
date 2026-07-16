# -*- coding: utf-8 -*-
"""pipebiz 采集模块单元测试。

仅测试纯函数解析逻辑，不测试真实 Playwright 页面操作（依赖网络）。
"""
import pytest


# ------------------------------------------------------------------
# parser 测试
# ------------------------------------------------------------------

MOCK_SEARCH_HTML_LIST = """
<html><body>
<ul class="list">
    <li>
        <a href="/zhaobiao/12345.html">XX市供水管网改造工程管材采购招标公告</a>
        <span class="date">2026-07-15</span>
        <span class="type">招标公告</span>
    </li>
    <li>
        <a href="/zhaobiao/12346.html">YY县雨污分流工程HDPE双壁波纹管采购</a>
        <span class="date">2026-07-14</span>
        <span class="type">中标公告</span>
    </li>
    <li>
        <a href="https://www.chinapipe.net/zhaobiao/12347.html">ZZ污水处理厂管道维修工程</a>
        <span class="date">2026/07/13</span>
    </li>
</ul>
</body></html>
"""


class TestParseSearchResults:
    """测试搜索结果列表解析。"""

    def test_parser_search_results(self):
        from scraper.pipebiz.parser import parse_search_results
        results = parse_search_results(MOCK_SEARCH_HTML_LIST)
        assert len(results) == 3

        # 第 1 条
        assert results[0]['project_name'] == 'XX市供水管网改造工程管材采购招标公告'
        assert '/zhaobiao/12345.html' in results[0]['source_url']
        assert results[0]['publish_date'] == '2026-07-15'
        assert results[0]['announcement_type'] == '招标公告'

        # 第 2 条
        assert '雨污分流' in results[1]['project_name']
        assert results[1]['publish_date'] == '2026-07-14'
        assert results[1]['announcement_type'] == '中标公告'

        # 第 3 条 — 绝对 URL
        assert results[2]['source_url'] == 'https://www.chinapipe.net/zhaobiao/12347.html'
        assert results[2]['publish_date'] == '2026-07-13'

    def test_parser_search_results_empty(self):
        from scraper.pipebiz.parser import parse_search_results
        assert parse_search_results('') == []
        assert parse_search_results(None) == []
        assert parse_search_results('<html><body></body></html>') == []

    def test_parser_search_results_table(self):
        from scraper.pipebiz.parser import parse_search_results
        html = """
        <html><body>
        <table>
        <tbody>
            <tr>
                <td><a href="/detail/100.html">管道安装工程项目招标</a></td>
                <td>2026-06-20</td>
            </tr>
            <tr>
                <td><a href="/detail/101.html">PVC管材采购公告</a></td>
                <td>2026-06-19</td>
            </tr>
        </tbody>
        </table>
        </body></html>
        """
        results = parse_search_results(html)
        assert len(results) == 2
        assert '管道安装' in results[0]['project_name']
        assert results[0]['publish_date'] == '2026-06-20'


MOCK_DETAIL_HTML = """
<html><body>
<div class="content">
    <h1>XX市供水管网改造工程管材采购招标公告</h1>
    <p>采购人：XX市自来水有限公司</p>
    <p>联系人：张三</p>
    <p>联系电话：0750-12345678</p>
    <p>预算金额：150万元</p>
    <p>项目地区：广东省江门市</p>
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
        from scraper.pipebiz.parser import parse_detail_page
        result = parse_detail_page(MOCK_DETAIL_HTML)

        assert result.get('buyer_name') == 'XX市自来水有限公司'
        assert result.get('contact_person') == '张三'
        assert result.get('phone') == '0750-12345678'
        assert '150' in result.get('budget_amount', '')
        assert '江门' in result.get('region', '')

    def test_parser_detail_page_attachments(self):
        from scraper.pipebiz.parser import parse_detail_page
        result = parse_detail_page(MOCK_DETAIL_HTML)

        attachments = result.get('attachments', [])
        assert len(attachments) >= 1
        urls = [a['url'] for a in attachments]
        assert any('招标文件' in u or 'pdf' in u for u in urls)

    def test_parser_detail_page_empty(self):
        from scraper.pipebiz.parser import parse_detail_page
        assert parse_detail_page('') == {}
        assert parse_detail_page(None) == {}


# ------------------------------------------------------------------
# utils 测试
# ------------------------------------------------------------------

class TestCleanPipebizText:
    """测试文本清理函数。"""

    def test_clean_pipebiz_text(self):
        from scraper.pipebiz.utils import clean_pipebiz_text

        assert clean_pipebiz_text('') == ''
        assert clean_pipebiz_text(None) == ''
        assert clean_pipebiz_text('  hello  world  ') == 'hello world'
        assert clean_pipebiz_text('test&nbsp;text') == 'test text'
        assert clean_pipebiz_text('<b>bold</b> text') == 'bold text'
        assert clean_pipebiz_text('line1\n  line2\t  line3') == 'line1 line2 line3'
        assert clean_pipebiz_text('&lt;tag&gt;') == ''  # decoded <tag> stripped as HTML tag

    def test_clean_pipebiz_text_complex(self):
        from scraper.pipebiz.utils import clean_pipebiz_text

        result = clean_pipebiz_text(
            '<p>XX市&nbsp;&nbsp;供水管网&nbsp;改造工程</p>'
        )
        assert result == 'XX市 供水管网 改造工程'


class TestParsePipebizDate:
    """测试日期解析函数。"""

    def test_parse_pipebiz_date(self):
        from scraper.pipebiz.utils import parse_pipebiz_date

        # 标准格式
        assert parse_pipebiz_date('2026-07-16') == ('2026-07-16', '')
        assert parse_pipebiz_date('2026/07/16') == ('2026-07-16', '')
        assert parse_pipebiz_date('2026.07.16') == ('2026-07-16', '')
        assert parse_pipebiz_date('2026年07月16日') == ('2026-07-16', '')

        # 带时间
        assert parse_pipebiz_date('2026-07-16 10:30:00') == ('2026-07-16', '10:30:00')
        assert parse_pipebiz_date('2026-07-16 10:30') == ('2026-07-16', '10:30:00')

        # 空值
        assert parse_pipebiz_date('') == ('', '')
        assert parse_pipebiz_date(None) == ('', '')
        assert parse_pipebiz_date('invalid') == ('', '')

    def test_parse_pipebiz_date_month_day(self):
        from scraper.pipebiz.utils import parse_pipebiz_date
        from datetime import datetime

        date_part, time_part = parse_pipebiz_date('07-16')
        assert date_part == f'{datetime.now().year}-07-16'
        assert time_part == ''


class TestExtractPipebizPhone:
    """测试电话提取函数。"""

    def test_extract_pipebiz_phone(self):
        from scraper.pipebiz.utils import extract_pipebiz_phone

        # 固话
        assert extract_pipebiz_phone('电话：0750-12345678') == '0750-12345678'
        assert extract_pipebiz_phone('联系方式 010 87654321') == '010 87654321'

        # 手机号
        assert extract_pipebiz_phone('联系人手机：13812345678') == '13812345678'
        assert extract_pipebiz_phone('138-1234-5678') == '138-1234-5678'

        # 400 电话
        assert extract_pipebiz_phone('客服热线：400-123-4567') == '400-123-4567'

        # 无电话
        assert extract_pipebiz_phone('') == ''
        assert extract_pipebiz_phone(None) == ''
        assert extract_pipebiz_phone('没有电话') == ''


# ------------------------------------------------------------------
# registry 测试
# ------------------------------------------------------------------

class TestRegistry:
    """测试 registry 注册。"""

    def test_registry_has_pipebiz(self):
        from scraper.registry import SCRAPER_REGISTRY
        assert 'pipebiz' in SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['pipebiz']
        assert entry['label'] == '管道商务网'
        assert entry['class_name'] == 'PipebizScraper'
        assert entry['badge_class'] == 'badge-indigo'
        assert entry['include_in_all'] is True
        assert entry['is_lead_source'] is True
        assert 'chinapipe.net' in entry['source_site']

    def test_scraper_class_import(self):
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('pipebiz')
        assert cls is not None
        assert cls.__name__ == 'PipebizScraper'

    def test_scraper_source_type(self):
        from scraper.pipebiz import PipebizScraper
        assert PipebizScraper.source_type == 'pipebiz'
        assert 'chinapipe.net' in PipebizScraper.base_url


# ------------------------------------------------------------------
# keywords 测试
# ------------------------------------------------------------------

class TestKeywords:
    """测试关键词配置。"""

    def test_pipebiz_keywords_exist(self):
        from scraper.keywords import PIPEBIZ_KEYWORDS_FINAL
        assert len(PIPEBIZ_KEYWORDS_FINAL) > 0
        assert '管道' in PIPEBIZ_KEYWORDS_FINAL or any('管' in kw for kw in PIPEBIZ_KEYWORDS_FINAL)
