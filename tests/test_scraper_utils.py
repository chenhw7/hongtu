# -*- coding: utf-8 -*-
"""scraper/utils.py 纯函数单元测试。"""
from datetime import date

import pytest
from bs4 import BeautifulSoup

from scraper.utils import (
    parse_date, parse_datetime, parse_amount, extract_attachments, safe_filename,
    strip_stage_suffix, extract_field, tokenized_bigrams,
)


class TestParseDate:
    """日期解析测试。"""

    def test_iso_format(self):
        assert parse_date('2026-07-15') == date(2026, 7, 15)

    def test_chinese_format(self):
        assert parse_date('2026年07月15日') == date(2026, 7, 15)

    def test_slash_format(self):
        assert parse_date('2026/07/15') == date(2026, 7, 15)

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date('') is None

    def test_invalid_format(self):
        assert parse_date('not-a-date') is None


class TestParseDatetime:
    """日期时间解析测试。"""

    def test_full_datetime(self):
        d, t = parse_datetime('2026-07-15 14:30:00')
        assert d == date(2026, 7, 15)
        assert t == '14:30'

    def test_date_time_no_seconds(self):
        d, t = parse_datetime('2026-07-15 14:30')
        assert d == date(2026, 7, 15)
        assert t == '14:30'

    def test_date_only(self):
        d, t = parse_datetime('2026-07-15')
        assert d == date(2026, 7, 15)
        assert t is None

    def test_none_input(self):
        d, t = parse_datetime(None)
        assert d is None
        assert t is None


class TestParseAmount:
    """金额解析测试。"""

    def test_simple_float(self):
        assert parse_amount('1234.56') == 1234.56

    def test_with_comma(self):
        assert parse_amount('1,234.56') == 1234.56

    def test_integer(self):
        assert parse_amount('1000') == 1000.0

    def test_none_input(self):
        assert parse_amount(None) is None

    def test_invalid(self):
        assert parse_amount('N/A') is None


class TestExtractAttachments:
    """附件提取测试。"""

    def test_extracts_pdf_links(self):
        html = '<a href="/files/doc.pdf">招标文件</a><a href="/page.html">页面</a>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_attachments(soup, 'http://example.com/bid/')
        assert len(result) == 1
        assert result[0]['name'] == '招标文件'
        assert result[0]['url'] == 'http://example.com/files/doc.pdf'

    def test_deduplicates_urls(self):
        html = '<a href="/files/doc.pdf">link1</a><a href="/files/doc.pdf">link2</a>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_attachments(soup, 'http://example.com/')
        assert len(result) == 1

    def test_skips_javascript_links(self):
        html = '<a href="javascript:void(0)">click</a><a href="/files/doc.pdf">doc</a>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_attachments(soup, 'http://example.com/')
        assert len(result) == 1

    def test_no_matching_links(self):
        html = '<a href="/page.html">page</a>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_attachments(soup, 'http://example.com/')
        assert result == []


class TestSafeFilename:
    """文件名清理测试。"""

    def test_strips_path_separators(self):
        result = safe_filename('a/b:c*d?e"f<g>h|i')
        assert '/' not in result
        assert '\\' not in result
        assert ':' not in result

    def test_truncates_long_names(self):
        long_name = 'x' * 200
        result = safe_filename(long_name)
        assert len(result) <= 150

    def test_uses_default_for_empty(self):
        assert safe_filename('') == 'attachment'
        assert safe_filename('  ') == 'attachment'

    def test_preserves_valid_name(self):
        assert safe_filename('招标文件_2026.pdf') == '招标文件_2026.pdf'


class TestStripStageSuffix:
    """项目名称阶段后缀剥离测试。"""

    def test_bare_bidding_suffix(self):
        """裸后缀：招标公告"""
        assert strip_stage_suffix('XX项目招标公告') == 'XX项目'

    def test_bare_eia_suffix(self):
        """裸后缀：环评公示"""
        assert strip_stage_suffix('XX项目环评公示') == 'XX项目'

    def test_bare_winner_suffix(self):
        """裸后缀：中标公告"""
        assert strip_stage_suffix('XX项目中标公告') == 'XX项目'

    def test_bare_acceptance_suffix(self):
        """裸后缀：验收公示"""
        assert strip_stage_suffix('XX项目验收公示') == 'XX项目'

    def test_half_width_paren_suffix(self):
        """半角括号包裹后缀"""
        assert strip_stage_suffix('XX项目(招标公告)') == 'XX项目'

    def test_full_width_paren_suffix(self):
        """全角括号包裹后缀"""
        assert strip_stage_suffix('XX项目（招标公告）') == 'XX项目'

    def test_stacked_suffixes(self):
        """后缀叠加：环评公示 + 招标公告"""
        assert strip_stage_suffix('XX项目(环评公示)招标公告') == 'XX项目'

    def test_stacked_bare_suffixes(self):
        """裸后缀叠加"""
        assert strip_stage_suffix('XX项目环评公示招标公告') == 'XX项目'

    def test_long_env_suffix(self):
        """长后缀：环境影响评价公示"""
        assert strip_stage_suffix('某工程环境影响评价公示') == '某工程'

    def test_no_suffix_unchanged(self):
        """无后缀时原样返回"""
        assert strip_stage_suffix('XX污水处理厂建设项目') == 'XX污水处理厂建设项目'

    def test_empty_input(self):
        assert strip_stage_suffix('') == ''

    def test_none_input(self):
        assert strip_stage_suffix(None) == ''

    def test_whitespace_stripped(self):
        """首尾空白应被清除"""
        assert strip_stage_suffix('  XX项目  ') == 'XX项目'

    def test_idempotent(self):
        """幂等性：对已剥离后缀的结果再次调用，结果不变"""
        assert strip_stage_suffix(strip_stage_suffix('XX项目招标公告')) == 'XX项目'
        assert strip_stage_suffix(strip_stage_suffix('XX项目(环评公示)')) == 'XX项目'
        assert strip_stage_suffix(strip_stage_suffix('XX项目')) == 'XX项目'

    def test_only_suffix(self):
        """名称仅由后缀组成时，剥离后为空"""
        assert strip_stage_suffix('招标公告') == ''

    def test_correction_notice(self):
        """更正公告"""
        assert strip_stage_suffix('XX项目更正公告') == 'XX项目'

    def test_competitive_consultation(self):
        """竞争性磋商"""
        assert strip_stage_suffix('XX项目竞争性磋商') == 'XX项目'


class TestExtractField:
    """extract_field 通用字段提取测试。"""

    def test_from_dict(self):
        """从 dict 提取字段"""
        obj = {'id': 1, 'project_name': 'XX项目', 'buyer_name': '某单位'}
        assert extract_field(obj, 'id') == 1
        assert extract_field(obj, 'project_name') == 'XX项目'

    def test_from_dict_missing_field(self):
        """dict 中不存在的字段返回空字符串"""
        obj = {'id': 1}
        assert extract_field(obj, 'nonexistent') == ''

    def test_from_dict_none_value(self):
        """dict 中值为 None 时返回空字符串"""
        obj = {'id': 1, 'project_name': None}
        assert extract_field(obj, 'project_name') == ''

    def test_from_object(self):
        """从 ORM 风格对象提取字段"""

        class FakeLead:
            def __init__(self):
                self.id = 42
                self.project_name = 'XX项目'

        obj = FakeLead()
        assert extract_field(obj, 'id') == 42
        assert extract_field(obj, 'project_name') == 'XX项目'

    def test_from_object_missing_attr(self):
        """对象不存在的属性返回空字符串"""

        class FakeLead:
            id = 1

        assert extract_field(FakeLead(), 'nonexistent') == ''


class TestTokenizedBigrams:
    """tokenized_bigrams 分词 2-gram 测试。"""

    def test_basic_chinese(self):
        """基本中文名称生成 2-gram"""
        grams = tokenized_bigrams('污水处理厂')
        assert '污水' in grams
        assert '水处' in grams
        assert '处理' in grams
        assert '理厂' in grams

    def test_punctuation_split(self):
        """按括号分隔，跨括号不生成 2-gram"""
        grams = tokenized_bigrams('XX(污水处理厂)')
        assert 'XX' in grams
        assert '污水' in grams
        # 跨边界的 "X(" 或 ")" 不应出现
        assert 'X(' not in grams
        assert '(污' not in grams

    def test_same_tokens_same_grams(self):
        """相同 token 不同顺序产生相同 2-gram 集合"""
        grams_a = tokenized_bigrams('XX(污水处理厂)')
        grams_b = tokenized_bigrams('污水处理厂(XX)')
        assert grams_a == grams_b

    def test_empty_input(self):
        assert tokenized_bigrams('') == set()

    def test_single_char(self):
        """单字符无法生成 2-gram"""
        assert tokenized_bigrams('A') == set()

    def test_mixed_delimiters(self):
        """多种分隔符混合"""
        grams = tokenized_bigrams('XX市-污水处理厂/扩建工程')
        assert 'XX市' not in grams  # 2-char token 只产生 1 个 bigram
        assert 'XX' in grams
        assert '污水' in grams
        assert '扩建' in grams
