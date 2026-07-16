# -*- coding: utf-8 -*-
"""scraper/keywords.py 关键词去重与组合逻辑单元测试。"""
import pytest
from scraper.keywords import (
    KEYWORD_CATEGORIES,
    CCGP_KEYWORDS,
    EIA_KEYWORDS,
    PLATFORM_KEYWORDS,
    CCGP_KEYWORDS_FINAL,
    EIA_KEYWORDS_FINAL,
    PLATFORM_KEYWORDS_FINAL,
    dedup_substring_keywords,
)


class TestKeywordCategories:
    """关键词分类完整性检查。"""

    def test_four_categories(self):
        assert len(KEYWORD_CATEGORIES) == 4
        assert set(KEYWORD_CATEGORIES.keys()) == {'product', 'engineering', 'project', 'material'}

    def test_total_keywords_around_50(self):
        all_keywords = set()
        for kws in KEYWORD_CATEGORIES.values():
            all_keywords.update(kws)
        assert 40 <= len(all_keywords) <= 60, f'预期 ~50 个关键词，实际 {len(all_keywords)}'

    def test_categories_not_empty(self):
        for cat, kws in KEYWORD_CATEGORIES.items():
            assert len(kws) > 0, f'分类 {cat} 为空'


class TestDedupSubstringKeywords:
    """子串去重逻辑测试。"""

    def test_removes_substring_duplicates(self):
        kws = ['管道', '市政管道', 'PVC管', '给水管', 'PE给水管']
        result = dedup_substring_keywords(kws)
        # '管道' ⊆ '市政管道'，应移除'管道'
        # '给水管' ⊆ 'PE给水管'，应移除'给水管'
        assert '管道' not in result
        assert '给水管' not in result
        assert '市政管道' in result
        assert 'PE给水管' in result
        assert 'PVC管' in result

    def test_no_false_positive_removal(self):
        kws = ['PVC管', 'HDPE管', 'PPR管']
        result = dedup_substring_keywords(kws)
        assert sorted(result) == sorted(kws)

    def test_empty_list(self):
        assert dedup_substring_keywords([]) == []

    def test_single_item(self):
        assert dedup_substring_keywords(['管道']) == ['管道']


class TestKeywordCombinations:
    """关键词组合逻辑测试。"""

    def test_ccgp_excludes_project_keywords(self):
        project_kws = set(KEYWORD_CATEGORIES['project'])
        ccgp_set = set(CCGP_KEYWORDS)
        # CCGP 不含项目类型词
        assert project_kws.isdisjoint(ccgp_set)

    def test_eia_only_project_plus_pipe(self):
        eia_set = set(EIA_KEYWORDS)
        project_kws = set(KEYWORD_CATEGORIES['project'])
        assert project_kws.issubset(eia_set)
        assert '管道' in eia_set
        # EIA 不应包含大量产品词
        product_kws = set(KEYWORD_CATEGORIES['product'])
        assert len(eia_set & product_kws) <= 1  # 最多只有'管道'

    def test_platform_includes_all(self):
        platform_set = set(PLATFORM_KEYWORDS)
        ccgp_set = set(CCGP_KEYWORDS)
        project_set = set(KEYWORD_CATEGORIES['project'])
        assert ccgp_set.issubset(platform_set)
        assert project_set.issubset(platform_set)

    def test_final_keywords_are_deduped(self):
        # 去重后的列表应 <= 原始列表
        assert len(CCGP_KEYWORDS_FINAL) <= len(CCGP_KEYWORDS)
        assert len(EIA_KEYWORDS_FINAL) <= len(EIA_KEYWORDS)
        assert len(PLATFORM_KEYWORDS_FINAL) <= len(PLATFORM_KEYWORDS)

    def test_no_duplicates_in_categories(self):
        all_kws = []
        for kws in KEYWORD_CATEGORIES.values():
            all_kws.extend(kws)
        assert len(all_kws) == len(set(all_kws)), '关键词跨分类有重复'
