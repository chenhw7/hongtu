# -*- coding: utf-8 -*-
"""scraper/utils.py 纯函数单元测试。"""
from datetime import date

import pytest
from bs4 import BeautifulSoup

from scraper.utils import parse_date, parse_datetime, parse_amount, extract_attachments, safe_filename


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
