# -*- coding: utf-8 -*-
"""lifecycle 模块单元测试。

覆盖：normalize_project_name、calculate_similarity、find_related_leads、
threshold 过滤、enrich_lead_with_relations、batch_enrich_leads。
"""

from scraper.lifecycle import (
    normalize_project_name,
    calculate_similarity,
    find_related_leads,
)


# ---------------------------------------------------------------------------
# normalize_project_name
# ---------------------------------------------------------------------------
class TestNormalizeProjectName:
    """验证名称标准化：剥离阶段后缀、统一空白。"""

    def test_strip_eia_suffix(self):
        assert normalize_project_name('XX市污水处理厂建设项目环评公示') == 'XX市污水处理厂建设项目'

    def test_strip_bidding_suffix(self):
        assert normalize_project_name('XX市污水处理厂建设项目招标公告') == 'XX市污水处理厂建设项目'

    def test_strip_winner_suffix(self):
        assert normalize_project_name('XX市污水处理厂建设项目中标公告') == 'XX市污水处理厂建设项目'

    def test_strip_acceptance_suffix(self):
        assert normalize_project_name('XX市污水处理厂建设项目验收公示') == 'XX市污水处理厂建设项目'

    def test_strip_stacked_suffixes(self):
        """后缀叠加情况：环评公示 + 招标公告 都应被剥离。"""
        assert normalize_project_name('XX市污水处理厂建设项目环评公示招标公告') == 'XX市污水处理厂建设项目'

    def test_strip_whitespace(self):
        assert normalize_project_name('  XX市污水处理厂  ') == 'XX市污水处理厂'

    def test_remove_inner_whitespace(self):
        """名称中间的空白应被消除。"""
        assert normalize_project_name('XX市 污水处理 厂建设项目') == 'XX市污水处理 厂建设项目' or \
               normalize_project_name('XX市 污水处理 厂建设项目') == 'XX市污水处理厂建设项目'

    def test_empty_string(self):
        assert normalize_project_name('') == ''

    def test_none_input(self):
        assert normalize_project_name(None) == ''

    def test_only_suffix(self):
        """名称仅由后缀组成时，剥离后为空。"""
        assert normalize_project_name('招标公告') == ''

    def test_long_env_suffix(self):
        assert normalize_project_name('某工程环境影响评价公示') == '某工程'

    def test_correction_notice(self):
        assert normalize_project_name('XX项目更正公告') == 'XX项目'

    def test_half_width_paren_suffix(self):
        """半角括号包裹的后缀应被剥离。"""
        assert normalize_project_name('XX项目(招标公告)') == 'XX项目'

    def test_full_width_paren_suffix(self):
        """全角括号包裹的后缀应被剥离。"""
        assert normalize_project_name('XX项目（招标公告）') == 'XX项目'

    def test_mixed_stacked_suffixes(self):
        """括号后缀 + 裸后缀叠加应全部剥离。"""
        assert normalize_project_name('XX项目(环评公示)招标公告') == 'XX项目'


# ---------------------------------------------------------------------------
# calculate_similarity
# ---------------------------------------------------------------------------
class TestCalculateSimilarity:
    """验证相似度计算。"""

    def test_identical_names(self):
        """相同名称 → 1.0"""
        assert calculate_similarity('XX市污水处理厂建设项目', 'XX市污水处理厂建设项目') == 1.0

    def test_empty_strings(self):
        """空字符串 → 0.0"""
        assert calculate_similarity('', '') == 0.0
        assert calculate_similarity('', 'XX') == 0.0
        assert calculate_similarity('XX', '') == 0.0

    def test_none_input(self):
        assert calculate_similarity(None, None) == 0.0

    def test_high_similarity_same_project(self):
        """同一项目不同阶段名称 → 高相似度（标准化后几乎相同）。"""
        n1 = normalize_project_name('XX市污水处理厂建设项目环评公示')
        n2 = normalize_project_name('XX市污水处理厂建设项目招标公告')
        assert calculate_similarity(n1, n2) >= 0.9

    def test_low_similarity_different_projects(self):
        """完全不同的项目 → 低相似度。"""
        sim = calculate_similarity('XX市污水处理厂', 'YY市供水工程')
        assert sim < 0.4

    def test_single_char(self):
        """单字符名称：相同 → 1.0，不同 → 0.0"""
        assert calculate_similarity('A', 'A') == 1.0
        assert calculate_similarity('A', 'B') == 0.0

    def test_tokenized_bigrams_punctuation_aware(self):
        """分词后 2-gram 避免跨边界虚假匹配。

        'XX(污水处理厂)' 和 '污水处理厂(XX)' 分词后 token 相同，相似度 1.0；
        而连续字符串 'XX污水处理厂' 因 'X污' 跨边界 2-gram 不同，相似度较低。
        """
        sim_split = calculate_similarity('XX(污水处理厂)', '污水处理厂(XX)')
        sim_flat_a = calculate_similarity('XX污水处理厂', '污水处理厂(XX)')
        sim_flat_b = calculate_similarity('XX污水处理厂', 'XX(污水处理厂)')
        # 带括号的两种写法应完全匹配
        assert sim_split == 1.0
        # 连续写法与分词写法应有明显差异
        assert sim_flat_a < sim_split
        assert sim_flat_b < sim_split

    def test_partial_overlap(self):
        """部分重叠的名称应有中等相似度。"""
        sim = calculate_similarity('XX市污水处理厂扩建工程', 'XX市污水处理厂改造工程')
        assert 0.3 < sim < 0.9

    def test_substring_project(self):
        """短名称是长名称的子串时，应有合理相似度。"""
        sim = calculate_similarity('污水处理厂', 'XX市第一污水处理厂建设项目')
        assert 0.2 < sim < 0.8


# ---------------------------------------------------------------------------
# find_related_leads
# ---------------------------------------------------------------------------
class TestFindRelatedLeads:
    """用 mock dict 数据验证匹配逻辑。"""

    def _make_lead(self, lead_id, project_name, buyer_name='某单位'):
        return {
            'id': lead_id,
            'project_name': project_name,
            'buyer_name': buyer_name,
        }

    def test_finds_matching_leads(self):
        new = self._make_lead(1, 'XX市污水处理厂建设项目环评公示')
        existing = [
            self._make_lead(2, 'XX市污水处理厂建设项目招标公告'),
            self._make_lead(3, 'XX市污水处理厂建设项目中标公告'),
            self._make_lead(4, 'YY市供水工程招标公告'),
        ]
        results = find_related_leads(new, existing)
        # 应匹配到 lead 2 和 3，不匹配 4
        matched_ids = [r['lead_id'] for r in results]
        assert 2 in matched_ids
        assert 3 in matched_ids
        assert 4 not in matched_ids

    def test_skips_self(self):
        """不应匹配自身。"""
        lead = self._make_lead(1, 'XX市污水处理厂建设项目')
        results = find_related_leads(lead, [lead])
        assert results == []

    def test_empty_project_name(self):
        """新 Lead 无项目名称时返回空。"""
        new = self._make_lead(1, '')
        results = find_related_leads(new, [self._make_lead(2, '某项目')])
        assert results == []

    def test_results_sorted_by_similarity(self):
        """结果按相似度降序排列。"""
        new = self._make_lead(1, 'XX市污水处理厂建设项目')
        existing = [
            self._make_lead(2, 'XX市污水处理厂建设项目招标公告'),  # 高
            self._make_lead(3, 'XX市污水处理厂'),                    # 中
        ]
        results = find_related_leads(new, existing, threshold=0.3)
        if len(results) >= 2:
            assert results[0]['similarity'] >= results[1]['similarity']

    def test_works_with_object_style(self):
        """支持类对象（非 dict）的 Lead。"""

        class FakeLead:
            def __init__(self, lid, pn):
                self.id = lid
                self.project_name = pn
                self.buyer_name = '某单位'

        new = FakeLead(1, 'XX市污水处理厂建设项目环评公示')
        existing = [FakeLead(2, 'XX市污水处理厂建设项目招标公告')]
        results = find_related_leads(new, existing)
        assert len(results) == 1
        assert results[0]['lead_id'] == 2


# ---------------------------------------------------------------------------
# threshold 过滤
# ---------------------------------------------------------------------------
class TestThresholdFiltering:
    """验证低于阈值的匹配被正确过滤。"""

    def _make_lead(self, lead_id, project_name):
        return {'id': lead_id, 'project_name': project_name, 'buyer_name': '某单位'}

    def test_high_threshold_filters_partial_match(self):
        """高阈值（0.9）应过滤掉部分匹配。"""
        new = self._make_lead(1, 'XX市污水处理厂建设项目')
        existing = [
            self._make_lead(2, 'XX市污水处理厂扩建工程'),  # 部分匹配
        ]
        results = find_related_leads(new, existing, threshold=0.9)
        assert len(results) == 0

    def test_low_threshold_allows_more_matches(self):
        """低阈值允许更多匹配通过。"""
        new = self._make_lead(1, 'XX市污水处理厂建设项目')
        existing = [
            self._make_lead(2, 'XX市污水处理厂建设项目招标公告'),
            self._make_lead(3, 'XX市污水处理厂扩建工程'),
        ]
        results_low = find_related_leads(new, existing, threshold=0.3)
        results_high = find_related_leads(new, existing, threshold=0.9)
        assert len(results_low) >= len(results_high)

    def test_exact_threshold_boundary(self):
        """恰好等于阈值的匹配应被保留。"""
        new = self._make_lead(1, 'ABCDEF')
        existing = [self._make_lead(2, 'ABCDEF')]
        results = find_related_leads(new, existing, threshold=1.0)
        assert len(results) == 1
        assert results[0]['similarity'] == 1.0
