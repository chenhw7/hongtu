# -*- coding: utf-8 -*-
"""中标方信息提取单元测试。

覆盖 ccgp extract_winner_info() 纯函数和 gdgpo 成交结果字段提升。
"""
import re
import unittest


from scraper.ccgp.detail import extract_winner_info
from scraper.gdgpo import _GPFA_RESULT_WINNER_RE


class TestCcgWinnerExtraction(unittest.TestCase):
    """ccgp 中标公告中标方提取测试。"""

    def test_winner_name_and_amount(self):
        """典型中标公告文本应同时提取到中标供应商名称和中标金额。"""
        text = (
            "某某市公共资源交易中心\n"
            "中标公告\n"
            "一、项目编号：XYZ-2026-001\n"
            "二、项目名称：办公设备采购项目\n"
            "三、中标信息\n"
            "中标供应商：深圳市某某科技有限公司\n"
            "中标金额：128.5万元\n"
            "四、主要标的信息\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result['winner_name'], '深圳市某某科技有限公司')
        self.assertAlmostEqual(result['winning_amount'], 1285000.0)

    def test_winner_name_chengjiao(self):
        """成交公告应使用'成交供应商'关键词提取。"""
        text = (
            "竞争性磋商成交公告\n"
            "成交供应商：广州某某建材有限公司\n"
            "成交金额：356000元\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result['winner_name'], '广州某某建材有限公司')
        self.assertAlmostEqual(result['winning_amount'], 356000.0)

    def test_winner_zhongbiao_danwei(self):
        """使用'中标单位'关键词的公告也能正确提取。"""
        text = (
            "中标结果公告\n"
            "中标单位：江门市某某工程有限公司\n"
            "中标金额：2,345,678.90元\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result['winner_name'], '江门市某某工程有限公司')
        # 千分位金额应正确解析
        self.assertAlmostEqual(result['winning_amount'], 2345678.90)

    def test_winner_amount_wan_yuan(self):
        """金额单位为万元时应正确转换为元。"""
        text = (
            "成交公告\n"
            "成交供应商：佛山某某设备有限公司\n"
            "成交金额：50.8万元\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result['winner_name'], '佛山某某设备有限公司')
        self.assertAlmostEqual(result['winning_amount'], 508000.0)

    def test_winner_amount_parsing_variants(self):
        """验证多种金额格式：千分位、无单位、带'元'单位等。"""
        # 千分位 + 元
        text1 = (
            "中标公告\n"
            "中标供应商：某某公司\n"
            "中标金额：1,234,567.89元\n"
        )
        r1 = extract_winner_info(text1)
        self.assertAlmostEqual(r1['winning_amount'], 1234567.89)

        # 无单位（纯数字），应保留原值（不转换）
        text2 = (
            "中标结果公告\n"
            "中标供应商：某某集团\n"
            "中标金额：999999\n"
        )
        r2 = extract_winner_info(text2)
        self.assertAlmostEqual(r2['winning_amount'], 999999.0)

    def test_no_winner_announcement(self):
        """非中标/成交公告应返回空 dict。"""
        text = (
            "采购公告\n"
            "一、项目编号：ABC-2026-001\n"
            "二、项目名称：信息化建设项目\n"
            "三、预算金额：500万元\n"
            "四、投标截止时间：2026年8月1日\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result, {})

    def test_winner_announcement_partial_info(self):
        """中标公告中只有名称没有金额时，应只返回名称。"""
        text = (
            "中标公告\n"
            "中标供应商：东莞某某材料有限公司\n"
            "地址：东莞市某某路123号\n"
        )
        result = extract_winner_info(text)
        self.assertEqual(result['winner_name'], '东莞某某材料有限公司')
        self.assertNotIn('winning_amount', result)

    def test_winner_name_with_trailing_noise(self):
        """中标供应商名称后紧跟'地址'等杂质时应截断。"""
        text = (
            "成交公告\n"
            "成交供应商：中山某某科技有限公司地址：中山市某某路\n"
            "成交金额：88万元\n"
        )
        result = extract_winner_info(text)
        # 应在'地址'处截断
        self.assertEqual(result['winner_name'], '中山某某科技有限公司')


class TestGdgpoWinnerLift(unittest.TestCase):
    """gdgpo 成交结果公告字段提升测试。"""

    def test_gpfa_result_winner_regex(self):
        """验证 _GPFA_RESULT_WINNER_RE 能匹配标准成交结果正文结构。"""
        text = (
            "二、成交供应商\n"
            "成交供应商\n"
            "地址\n"
            "成交金额（元）\n"
            "广州某某信息技术有限公司\n"
            "广州市天河区某某路100号\n"
            "568000.00"
        )
        match = _GPFA_RESULT_WINNER_RE.search(text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).strip(), '广州某某信息技术有限公司')
        self.assertEqual(match.group(2).strip(), '广州市天河区某某路100号')
        self.assertEqual(match.group(3).strip(), '568000.00')

    def test_gpfa_result_winner_amount_with_comma(self):
        """成交金额带千分位逗号时应能被正则匹配。"""
        text = (
            "二、成交供应商\n"
            "成交供应商\n"
            "地址\n"
            "成交金额（元）\n"
            "深圳某某科技股份有限公司\n"
            "深圳市南山区某某大道1号\n"
            "1,234,567.89"
        )
        match = _GPFA_RESULT_WINNER_RE.search(text)
        self.assertIsNotNone(match)
        amount_str = match.group(3).replace(',', '')
        self.assertAlmostEqual(float(amount_str), 1234567.89)

    def test_gpfa_result_no_match(self):
        """非成交结果正文不应匹配。"""
        text = (
            "一、项目基本情况\n"
            "项目名称：办公设备采购\n"
            "二、征集人信息\n"
            "征集人：某某采购中心\n"
        )
        match = _GPFA_RESULT_WINNER_RE.search(text)
        self.assertIsNone(match)


if __name__ == '__main__':
    unittest.main()
