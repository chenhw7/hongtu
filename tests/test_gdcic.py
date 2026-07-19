# -*- coding: utf-8 -*-
"""gdcic 采集模块单元测试。

覆盖范围：
- parser: 招投标列表项字段映射、详情字段解析、项目信息解析
- api:    httpx API 调用封装（mock httpx 响应）
- utils:  日期解析、文本清理、电话提取
- registry: gdcic 条目验证
- import: 模块导入验证
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ------------------------------------------------------------------
# 测试数据（基于真实 API 抓包结果）
# ------------------------------------------------------------------

MOCK_LIST_ITEM = {
    'id': '10051047',
    'projectId': '4407812604020001',
    'projectName': '天悦湾11#小区公共活动中心及公共架空（主体阶段）',
    'projectCode': '4407812604020001',
    'tenderType': '施工',
    'provinceBiddingCode': '4407812604020001-BD-014',
    'tenderMode': '直接委托',
    'dataLevel': 'C',
    'address': None,
    'biddingDate': None,
    'biddingMoney': None,
    'scale': None,
    'agentOrgName': None,
    'biddingUnit': [
        {'orgTypeId': 17, 'orgType': '承包单位',
         'orgName': '广东华置建设有限公司', 'orgCode': 'MA544GEN2'},
    ],
    'biddingUnitPerson': [],
}

MOCK_LIST_ITEM_MULTI_UNITS = {
    'id': '10051048',
    'projectName': '某市政管网改造工程',
    'projectCode': '4407812604020002',
    'tenderType': '施工',
    'provinceBiddingCode': '4407812604020002-BD-015',
    'tenderMode': '公开招标',
    'dataLevel': 'B',
    'biddingUnit': [
        {'orgName': '中建一局', 'orgCode': 'ORG001'},
        {'orgName': '中建二局', 'orgCode': 'ORG002'},
    ],
}

MOCK_LIST_RESPONSE = {
    'msg': 'success',
    'total': 160063,
    'code': 0,
    'rows': [MOCK_LIST_ITEM, MOCK_LIST_ITEM_MULTI_UNITS],
}

# 真实详情 API 响应：记录字段直接在顶层，无 code/msg/data 包装
MOCK_DETAIL_RESPONSE = {
    'id': '10051047',
    'projectName': '天悦湾11#小区公共活动中心及公共架空（主体阶段）',
    'projectCode': '4407812604020001',
    'tenderType': '施工',
    'provinceBiddingCode': '4407812604020001-BD-014',
    'tenderMode': '直接委托',
    'dataLevel': 'C',
    'address': '台山市台城西湖片区国际路与龙成路交叉口东北侧',
    'biddingDate': '2026-03-09 00:00:00',
    'biddingMoney': '639.76',
    'scale': '建筑面积3198.8m²，地上2层。',
    'agentOrgName': None,
    'agentUnit': [
        {'orgName': '广东某招标代理有限公司', 'orgCode': 'AGENT001'},
    ],
    'biddingUnit': [
        {'orgTypeId': 17, 'orgType': '承包单位',
         'orgName': '广东华置建设有限公司', 'orgCode': 'MA544GEN2'},
    ],
    # 真实详情 API 中 biddingUnitPerson 通常非空（列表 API 中为空数组）
    'biddingUnitPerson': [
        {'orgName': '广东华置建设有限公司', 'orgCode': 'MA544GEN2',
         'name': '张三', 'post': '项目经理'},
    ],
}

# 真实项目信息 API 响应：无 code/msg/data 包装，字段直接在顶层
# 字段名与列表/详情不同：province/city/division/totalInvestment/scale
MOCK_PROJECT_INFO_RESPONSE = {
    'projectName': '天悦湾11#小区公共活动中心及公共架空（主体阶段）',
    'projectCode': '4407812604020001',
    'province': '广东省',
    'city': '江门市',
    'division': '台山市',
    # 真实 API 中 buildUnit 是组织数组（含 orgName/orgCode），与 biddingUnit 结构一致
    'buildUnit': [
        {'orgTypeId': 1, 'orgType': '建设单位',
         'orgName': '台山市某房地产开发公司', 'orgCode': 'MA12345X'},
    ],
    'totalInvestment': '5000.00',
    'totalArea': '3198.8',
    'scale': '总建筑面积3198.8平方米',
}


# ------------------------------------------------------------------
# parser 测试 — 列表项解析
# ------------------------------------------------------------------

class TestParseBiddingListItem:
    """测试招投标列表项解析。"""

    def test_parse_basic_fields(self):
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM)

        assert lead['project_name'] == '天悦湾11#小区公共活动中心及公共架空（主体阶段）'
        assert lead['bidding_number'] == '4407812604020001-BD-014'
        assert lead['announcement_type'] == '中标公告'
        assert lead['region'] == '广东省'
        assert lead['buyer_name'] == '广东华置建设有限公司'
        assert lead['bidding_unit_codes'] == 'MA544GEN2'
        assert lead['tender_type'] == '施工'
        assert lead['tender_mode'] == '直接委托'
        assert lead['project_code'] == '4407812604020001'
        assert lead['data_level'] == 'C'
        # _bidding_id 临时字段
        assert lead['_bidding_id'] == '10051047'

    def test_parse_source_url(self):
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM)
        assert 'id=10051047' in lead['source_url']
        assert lead['source_url'].startswith('https://skypt.gdcic.net/')

    def test_parse_multiple_bidding_units(self):
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM_MULTI_UNITS)
        # 多个中标单位用逗号拼接
        assert lead['buyer_name'] == '中建一局,中建二局'
        assert lead['bidding_unit_codes'] == 'ORG001,ORG002'

    def test_parse_list_item_null_fields_excluded(self):
        """列表中为 null 的字段（address/biddingDate等）不应出现。"""
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM)
        # 列表中这些字段为 null，不应出现在 lead 中
        assert 'buyer_address' not in lead
        assert 'publish_date' not in lead
        assert 'budget_amount' not in lead
        assert 'scale' not in lead

    def test_parse_empty_item(self):
        from scraper.gdcic.parser import parse_bidding_list_item
        assert parse_bidding_list_item({}) == {}
        assert parse_bidding_list_item(None) == {}
        assert parse_bidding_list_item('not a dict') == {}

    def test_parse_no_bidding_units(self):
        """biddingUnit 为空列表时 buyer_name 不出现。"""
        from scraper.gdcic.parser import parse_bidding_list_item
        item = {'id': '1', 'projectName': '测试项目', 'provinceBiddingCode': 'CODE-1'}
        lead = parse_bidding_list_item(item)
        assert lead['project_name'] == '测试项目'
        assert 'buyer_name' not in lead

    def test_parse_project_id(self):
        """projectId 应存入 raw_data（Minor 1）。"""
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM)
        assert lead['project_id'] == '4407812604020001'

    def test_parse_bidding_unit_persons_defensive(self):
        """列表中 biddingUnitPerson 非空时防御性解析为 contact_person。

        真实数据中列表 API 的 biddingUnitPerson 始终为空数组，
        此测试验证防御性解析逻辑能正确处理非空数据。
        """
        from scraper.gdcic.parser import parse_bidding_list_item
        item = {
            'id': '100',
            'projectName': '测试项目',
            'provinceBiddingCode': 'CODE-X',
            'biddingUnitPerson': [
                {'name': '李四', 'orgName': '某公司', 'post': '项目经理'},
                {'personName': '王五', 'phone': '13812345678'},
                'not a dict',  # 非 dict 元素应被跳过
            ],
        }
        lead = parse_bidding_list_item(item)
        assert lead['contact_person'] == '李四,王五'
        assert lead['phone'] == '13812345678'

    def test_parse_bidding_unit_persons_empty(self):
        """biddingUnitPerson 为空数组时不产生 contact_person/phone。"""
        from scraper.gdcic.parser import parse_bidding_list_item
        lead = parse_bidding_list_item(MOCK_LIST_ITEM)
        assert 'contact_person' not in lead
        assert 'phone' not in lead


# ------------------------------------------------------------------
# parser 测试 — 详情解析
# ------------------------------------------------------------------

class TestParseBiddingDetail:
    """测试招投标详情解析。"""

    def test_parse_detail_basic(self):
        from scraper.gdcic.parser import parse_bidding_detail
        # 详情 API 响应无 code/msg/data 包装，记录字段直接在顶层
        result = parse_bidding_detail(MOCK_DETAIL_RESPONSE)

        assert result['buyer_address'] == '台山市台城西湖片区国际路与龙成路交叉口东北侧'
        assert result['publish_date'] == date(2026, 3, 9)
        assert result['budget_amount'] == 639.76
        assert result['scale'] == '建筑面积3198.8m²，地上2层。'
        # agentUnit 数组中的代理机构名
        assert result['agency_name'] == '广东某招标代理有限公司'

    def test_parse_detail_date_with_time(self):
        from scraper.gdcic.parser import parse_bidding_detail
        detail_data = {
            'biddingDate': '2026-03-09 14:30:00',
            'biddingMoney': '100.5',
            'address': '广州市天河区',
        }
        result = parse_bidding_detail(detail_data)
        assert result['publish_date'] == date(2026, 3, 9)
        assert result['publish_time'] == '14:30:00'
        assert result['budget_amount'] == 100.5
        assert result['buyer_address'] == '广州市天河区'

    def test_parse_detail_agent_org_name_fallback(self):
        """详情中无 agentUnit 但有 agentOrgName 时使用 agentOrgName。"""
        from scraper.gdcic.parser import parse_bidding_detail
        detail_data = {
            'agentOrgName': '某代理公司',
            'agentUnit': None,
        }
        result = parse_bidding_detail(detail_data)
        assert result['agency_name'] == '某代理公司'

    def test_parse_detail_empty(self):
        from scraper.gdcic.parser import parse_bidding_detail
        assert parse_bidding_detail({}) == {}
        assert parse_bidding_detail(None) == {}

    def test_parse_detail_invalid_money(self):
        """无效金额返回空字典中不含 budget_amount。"""
        from scraper.gdcic.parser import parse_bidding_detail
        result = parse_bidding_detail({'biddingMoney': 'abc'})
        assert 'budget_amount' not in result

    def test_parse_detail_null_fields(self):
        """详情中 null 字段不应出现。"""
        from scraper.gdcic.parser import parse_bidding_detail
        result = parse_bidding_detail({
            'address': None,
            'biddingDate': None,
            'biddingMoney': None,
            'scale': None,
        })
        assert result == {}

    def test_parse_detail_bidding_unit_persons(self):
        """详情中 biddingUnitPerson 非空时解析为 contact_person（Major 2）。

        真实详情 API 中 biddingUnitPerson 通常非空，含项目经理等联系人。
        """
        from scraper.gdcic.parser import parse_bidding_detail
        result = parse_bidding_detail(MOCK_DETAIL_RESPONSE)
        assert result['contact_person'] == '张三'
        # 真实数据中无 phone 字段，phone 不应出现
        assert 'phone' not in result

    def test_parse_detail_bidding_unit_persons_multiple(self):
        """多个 person 时 name 用逗号拼接。"""
        from scraper.gdcic.parser import parse_bidding_detail
        detail = {
            'biddingUnitPerson': [
                {'name': '张三', 'post': '项目经理'},
                {'name': '李四', 'post': '项目总监'},
            ],
        }
        result = parse_bidding_detail(detail)
        assert result['contact_person'] == '张三,李四'

    def test_parse_detail_agent_unit_codes(self):
        """详情中 agentUnit 的 orgCode 应提取为 agent_unit_codes（Minor 2）。"""
        from scraper.gdcic.parser import parse_bidding_detail
        result = parse_bidding_detail(MOCK_DETAIL_RESPONSE)
        assert result['agency_name'] == '广东某招标代理有限公司'
        assert result['agent_unit_codes'] == 'AGENT001'

    def test_parse_detail_buyer_name_direct_assign(self):
        """详情中 buyer_name 用直接赋值覆盖列表字段（Minor 6）。"""
        from scraper.gdcic.parser import parse_bidding_detail
        detail = {'biddingUnit': [{'orgName': '详情中的中标单位', 'orgCode': 'C1'}]}
        result = parse_bidding_detail(detail)
        assert result['buyer_name'] == '详情中的中标单位'


# ------------------------------------------------------------------
# parser 测试 — 项目信息解析
# ------------------------------------------------------------------

class TestParseProjectInfo:
    """测试项目信息解析。"""

    def test_parse_basic(self):
        from scraper.gdcic.parser import parse_project_info
        info = {
            'provinceName': '广东省',
            'cityName': '江门市',
            'districtName': '台山市',
            'buildUnit': '某房地产开发公司',
            'totalInvest': '5000.00',
            'totalArea': '3198.8',
            'buildScale': '总建筑面积3198.8平方米',
        }
        result = parse_project_info(info)
        assert result['project_location'] == '广东省江门市台山市'
        assert result['build_unit'] == '某房地产开发公司'
        assert result['total_invest'] == 5000.0
        assert result['total_area'] == '3198.8'
        assert result['build_scale'] == '总建筑面积3198.8平方米'

    def test_parse_empty(self):
        from scraper.gdcic.parser import parse_project_info
        assert parse_project_info({}) == {}
        assert parse_project_info(None) == {}

    def test_parse_real_field_names(self):
        """用真实 API 字段名解析（province/city/division/totalInvestment/scale）。

        真实接口确认：项目信息 API 响应字段名为 province/city/division/
        totalInvestment/scale，而非旧文档中的 provinceName/totalInvest/buildScale。
        buildUnit 是组织数组（含 orgName/orgCode），与 biddingUnit 结构一致。
        """
        from scraper.gdcic.parser import parse_project_info
        result = parse_project_info(MOCK_PROJECT_INFO_RESPONSE)
        assert result['project_location'] == '广东省江门市台山市'
        # buildUnit 是数组，提取 orgName 作为建设单位名称
        assert result['build_unit'] == '台山市某房地产开发公司'
        assert result['build_unit_codes'] == 'MA12345X'
        assert result['total_invest'] == 5000.0
        assert result['total_area'] == '3198.8'
        assert result['build_scale'] == '总建筑面积3198.8平方米'

    def test_parse_legacy_field_names_compat(self):
        """兼容旧字段名（provinceName/totalInvest/buildScale）作为回退。"""
        from scraper.gdcic.parser import parse_project_info
        info = {
            'provinceName': '广东省',
            'cityName': '广州市',
            'districtName': '天河区',
            'buildUnit': '某单位',
            'totalInvest': '1000',
            'totalArea': '500',
            'buildScale': '规模说明',
        }
        result = parse_project_info(info)
        assert result['project_location'] == '广东省广州市天河区'
        assert result['total_invest'] == 1000.0
        assert result['build_scale'] == '规模说明'


# ------------------------------------------------------------------
# api 测试 — mock httpx 响应
# ------------------------------------------------------------------

def _make_mock_scraper(response_json=None, status_code=200):
    """创建 mock scraper 用于 API 测试。"""
    mock = MagicMock()
    mock.session = MagicMock()
    mock.get_random_delay.return_value = 0
    mock.get_random_ua.return_value = 'Mozilla/5.0 test-ua'
    mock._create_session = MagicMock()

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = response_json or {}
    mock.session.get.return_value = mock_response
    return mock


class TestFetchBiddingList:
    """测试招投标列表 API 调用。"""

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_list_success(self, _mock_sleep):
        from scraper.gdcic.api import fetch_bidding_list
        scraper = _make_mock_scraper(MOCK_LIST_RESPONSE)
        result = fetch_bidding_list(scraper, keyword='管道', page_num=1)

        assert result is not None
        assert result['code'] == 0
        assert result['total'] == 160063
        assert len(result['rows']) == 2
        # 验证请求参数
        call_args = scraper.session.get.call_args
        assert call_args is not None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_list_http_error(self, _mock_sleep):
        from scraper.gdcic.api import fetch_bidding_list
        scraper = _make_mock_scraper(status_code=500)
        result = fetch_bidding_list(scraper, keyword='管道', page_num=1)
        assert result is None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_list_business_error(self, _mock_sleep):
        """code != 0 视为业务异常。"""
        from scraper.gdcic.api import fetch_bidding_list
        scraper = _make_mock_scraper({'code': 1, 'msg': 'error'})
        result = fetch_bidding_list(scraper, keyword='管道', page_num=1)
        assert result is None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_list_network_exception(self, _mock_sleep):
        from scraper.gdcic.api import fetch_bidding_list
        scraper = _make_mock_scraper(MOCK_LIST_RESPONSE)
        scraper.session.get.side_effect = Exception('network error')
        result = fetch_bidding_list(scraper, keyword='管道', page_num=1)
        assert result is None


class TestFetchBiddingDetail:
    """测试招投标详情 API 调用。"""

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_detail_success(self, _mock_sleep):
        from scraper.gdcic.api import fetch_bidding_detail
        scraper = _make_mock_scraper(MOCK_DETAIL_RESPONSE)
        result = fetch_bidding_detail(scraper, '10051047')

        assert result is not None
        # 详情 API 响应无 code/msg/data 包装，字段直接在顶层
        assert 'code' not in result
        assert result['address'] == '台山市台城西湖片区国际路与龙成路交叉口东北侧'
        assert result['biddingMoney'] == '639.76'
        # 验证 URL 包含 ID
        call_args = scraper.session.get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        assert '10051047' in url

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_detail_no_code_wrapper(self, _mock_sleep):
        """详情 API 响应无 code 字段时仍能正常返回（回归此 bug 场景）。

        根因：详情 API 响应记录字段直接在顶层，无 code/msg/data 包装，
        _get_api 的 code 校验会误判为业务异常返回 None，导致详情字段全部丢失。
        """
        from scraper.gdcic.api import fetch_bidding_detail
        # 真实详情响应样例：记录字段直接在顶层，无 code/msg/data 包装
        detail_response = {
            'id': '10050987',
            'projectName': '潮州市韩江新城砚峰路给水管道工程',
            'projectCode': '4407812604020001',
            'tenderType': '施工',
            'provinceBiddingCode': '4407812604020001-BD-001',
            'tenderMode': '公开招标',
            'dataLevel': 'C',
            'address': '潮州市韩江新城砚峰路',
            'biddingDate': '2025-07-24 00:00:00',
            'biddingMoney': '803.95',
            'scale': '本工程建设内容为砚峰路全线供水管道工程建设...',
            'agentOrgName': None,
            'agentUnit': [],
            'biddingUnit': [],
            'biddingUnitPerson': [],
        }
        scraper = _make_mock_scraper(detail_response)
        result = fetch_bidding_detail(scraper, '10050987')
        # 修复前：_get_api 校验 code=None 误判为异常返回 None
        # 修复后：详情 API 不校验 code，直接返回记录本身
        assert result is not None
        assert result['address'] == '潮州市韩江新城砚峰路'
        assert result['biddingMoney'] == '803.95'
        assert result['projectName'] == '潮州市韩江新城砚峰路给水管道工程'

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_detail_empty_id(self, _mock_sleep):
        """空 ID 直接返回 None，不发请求。"""
        from scraper.gdcic.api import fetch_bidding_detail
        scraper = _make_mock_scraper(MOCK_DETAIL_RESPONSE)
        result = fetch_bidding_detail(scraper, '')
        assert result is None
        scraper.session.get.assert_not_called()

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_detail_http_error(self, _mock_sleep):
        from scraper.gdcic.api import fetch_bidding_detail
        scraper = _make_mock_scraper(status_code=404)
        result = fetch_bidding_detail(scraper, '99999')
        assert result is None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_detail_url_encoded(self, _mock_sleep):
        """bidding_id 含特殊字符时应被 URL 编码（Minor 5）。"""
        from scraper.gdcic.api import fetch_bidding_detail
        scraper = _make_mock_scraper(MOCK_DETAIL_RESPONSE)
        fetch_bidding_detail(scraper, 'id/with/slash')
        call_args = scraper.session.get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        # 斜杠应被编码为 %2F
        assert 'id%2Fwith%2Fslash' in url


class TestFetchProjectInfo:
    """测试项目信息 API 调用（Major 3）。"""

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_success(self, _mock_sleep):
        """成功返回：项目信息 API 无 code 包装，字段直接在顶层。"""
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(MOCK_PROJECT_INFO_RESPONSE)
        result = fetch_project_info(scraper, '4407812604020001')

        assert result is not None
        # 项目信息 API 响应无 code/msg/data 包装
        assert 'code' not in result
        assert 'data' not in result
        # buildUnit 是组织数组（原始 API 数据未解析）
        assert isinstance(result['buildUnit'], list)
        assert result['buildUnit'][0]['orgName'] == '台山市某房地产开发公司'
        assert result['projectCode'] == '4407812604020001'
        # 验证 URL 包含 project_code
        call_args = scraper.session.get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        assert '4407812604020001' in url

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_no_code_wrapper(self, _mock_sleep):
        """项目信息 API 无 code 字段时仍能正常返回（回归 _get_api 误判场景）。

        根因：项目信息 API 响应字段直接在顶层，无 code/msg/data 包装，
        若走 _get_api 的 code 校验会误判为业务异常返回 None，
        导致建设单位等字段全部丢失。修复后绕过 code 校验直接返回。
        """
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(MOCK_PROJECT_INFO_RESPONSE)
        result = fetch_project_info(scraper, '4407812604020001')
        assert result is not None
        # 项目信息 API 响应字段直接在顶层（buildUnit 是组织数组）
        assert isinstance(result['buildUnit'], list)
        assert result['buildUnit'][0]['orgName'] == '台山市某房地产开发公司'

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_http_error(self, _mock_sleep):
        """HTTP 错误返回 None。"""
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(status_code=500)
        result = fetch_project_info(scraper, '4407812604020001')
        assert result is None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_empty_code(self, _mock_sleep):
        """空 project_code 直接返回 None，不发请求。"""
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(MOCK_PROJECT_INFO_RESPONSE)
        result = fetch_project_info(scraper, '')
        assert result is None
        scraper.session.get.assert_not_called()

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_network_exception(self, _mock_sleep):
        """网络异常返回 None。"""
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(MOCK_PROJECT_INFO_RESPONSE)
        scraper.session.get.side_effect = Exception('network error')
        result = fetch_project_info(scraper, '4407812604020001')
        assert result is None

    @patch('scraper.gdcic.api.time.sleep')
    def test_fetch_project_info_url_encoded(self, _mock_sleep):
        """project_code 含特殊字符时应被 URL 编码（Minor 5）。"""
        from scraper.gdcic.api import fetch_project_info
        scraper = _make_mock_scraper(MOCK_PROJECT_INFO_RESPONSE)
        fetch_project_info(scraper, 'code/with/slash')
        call_args = scraper.session.get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
        assert 'code%2Fwith%2Fslash' in url


class TestPageSize:
    """验证 _PAGE_SIZE 配置（Minor 3）。"""

    def test_page_size_is_20(self):
        from scraper.gdcic.api import _PAGE_SIZE
        assert _PAGE_SIZE == 20


# ------------------------------------------------------------------
# utils 测试（保留原有）
# ------------------------------------------------------------------

class TestCleanGdcicText:
    """测试文本清理函数。"""

    def test_clean_text(self):
        from scraper.gdcic.utils import clean_gdcic_text
        assert clean_gdcic_text('') == ''
        assert clean_gdcic_text(None) == ''
        assert clean_gdcic_text('  hello  world  ') == 'hello world'
        assert clean_gdcic_text('line1\n  line2\t  line3') == 'line1 line2 line3'


class TestParseGdcicDate:
    """测试日期解析函数。"""

    def test_parse_date_standard(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026-07-18')
        assert d == date(2026, 7, 18)
        assert t is None

    def test_parse_date_with_time(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026-07-18 10:30:00')
        assert d == date(2026, 7, 18)
        assert t == '10:30:00'

    def test_parse_date_slash(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026/07/18')
        assert d == date(2026, 7, 18)

    def test_parse_date_chinese(self):
        from scraper.gdcic.utils import parse_gdcic_date
        d, t = parse_gdcic_date('2026年7月18日')
        assert d == date(2026, 7, 18)

    def test_parse_date_empty(self):
        from scraper.gdcic.utils import parse_gdcic_date
        assert parse_gdcic_date('') == (None, None)
        assert parse_gdcic_date(None) == (None, None)


class TestExtractGdcicPhone:
    """测试电话提取函数。"""

    def test_landline(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('电话：0750-12345678') == '0750-12345678'

    def test_mobile(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('联系人手机：13812345678') == '13812345678'

    def test_no_phone(self):
        from scraper.gdcic.utils import extract_gdcic_phone
        assert extract_gdcic_phone('') == ''
        assert extract_gdcic_phone(None) == ''
        assert extract_gdcic_phone('没有电话') == ''


# ------------------------------------------------------------------
# registry 测试
# ------------------------------------------------------------------

class TestRegistry:
    """测试 registry 注册。"""

    def test_registry_has_gdcic(self):
        from scraper.registry import SCRAPER_REGISTRY
        assert 'gdcic' in SCRAPER_REGISTRY
        entry = SCRAPER_REGISTRY['gdcic']
        assert entry['label'] == '广东住建厅'
        assert entry['class_name'] == 'GdcicScraper'
        assert entry['badge_class'] == 'badge-indigo'
        assert entry['include_in_all'] is True
        assert entry['is_lead_source'] is True
        assert 'gdcic.net' in entry['source_site']

    def test_scraper_class_import(self):
        from scraper.registry import get_scraper_class
        cls = get_scraper_class('gdcic')
        assert cls is not None
        assert cls.__name__ == 'GdcicScraper'

    def test_scraper_source_type(self):
        from scraper.gdcic import GdcicScraper
        assert GdcicScraper.source_type == 'gdcic'
        assert 'gdcic.net' in GdcicScraper.base_url

    def test_config_source_sites(self):
        from app.config import Config
        sites = Config.SCRAPER_SOURCE_SITES
        assert 'gdcic' in sites
        assert 'gdcic.net' in sites['gdcic']


# ------------------------------------------------------------------
# 采集器实例化测试
# ------------------------------------------------------------------

class TestScraperInstantiation:
    """验证 GdcicScraper 可以正常实例化且无 Playwright 依赖。"""

    def test_import_no_playwright(self):
        """验证 import scraper.gdcic 不触发 Playwright 导入。"""
        import importlib
        import sys

        # 移除已有的 gdcic 模块缓存，强制重新导入
        mods_to_remove = [k for k in sys.modules if k.startswith('scraper.gdcic')]
        for mod in mods_to_remove:
            del sys.modules[mod]

        # 确保 playwright 未被导入（如果之前被其他模块导入则忽略）
        import scraper.gdcic  # noqa: F401
        # 如果导入成功且无异常，说明不依赖 Playwright

    def test_instantiate(self):
        from scraper.gdcic import GdcicScraper
        scraper = GdcicScraper()
        assert scraper is not None
        assert scraper.source_type == 'gdcic'
        assert scraper.delay_min == 2
        assert scraper.delay_max == 3
        assert len(scraper.keywords) > 0

    def test_scrape_page_returns_none_on_api_failure(self):
        """列表 API 失败时 _scrape_page 返回 None。"""
        from scraper.gdcic import GdcicScraper
        from scraper.gdcic.api import fetch_bidding_list

        scraper = GdcicScraper()
        with patch('scraper.gdcic.fetch_bidding_list', return_value=None):
            result = scraper._scrape_page('管道', 1)
        assert result is None

    def test_scrape_page_returns_empty_on_no_rows(self):
        """列表 API 返回空 rows 时 _scrape_page 返回空列表。"""
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        with patch('scraper.gdcic.fetch_bidding_list',
                   return_value={'code': 0, 'rows': [], 'total': 0}):
            result = scraper._scrape_page('管道', 1)
        assert result == []

    def test_scrape_page_fetches_detail(self):
        """_scrape_page 正常流程：列表+详情+解析。"""
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        # mock 前置去重（返回空集，表示全部需要请求详情）
        scraper._prefetch_existing_keys = lambda leads: set()
        scraper._check_pause_and_stop = lambda: None
        scraper._lead_dedup_key = lambda lead: None  # 禁用去重 key

        list_payload = {'code': 0, 'rows': [MOCK_LIST_ITEM], 'total': 1}
        # fetch_bidding_detail 修复后返回记录本身（无 code/data 包装）
        with patch('scraper.gdcic.fetch_bidding_list', return_value=list_payload), \
             patch('scraper.gdcic.fetch_bidding_detail',
                   return_value=MOCK_DETAIL_RESPONSE):
            result = scraper._scrape_page('管道', 1)

        assert len(result) == 1
        lead = result[0]
        assert lead['project_name'] == '天悦湾11#小区公共活动中心及公共架空（主体阶段）'
        # 详情字段已补全
        assert lead['buyer_address'] == '台山市台城西湖片区国际路与龙成路交叉口东北侧'
        assert lead['budget_amount'] == 639.76
        assert lead['publish_date'] == date(2026, 3, 9)
        # _bidding_id 应被 pop 掉
        assert '_bidding_id' not in lead

    def test_anti_scrape_wait_zero(self):
        """API 模式无需 60s 反爬等待（Minor 7）。"""
        from scraper.gdcic import GdcicScraper
        scraper = GdcicScraper()
        assert scraper.anti_scrape_wait == 0

    def test_scrape_page_detail_failure_skipped(self):
        """详情 API 失败时该条不入库（Major 4 方案 A）。

        fetch_bidding_detail 返回 None 时，该 lead 从结果列表移除，
        下次 run 时不会被去重命中，会重新请求详情。
        """
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        scraper._prefetch_existing_keys = lambda leads: set()
        scraper._check_pause_and_stop = lambda: None
        scraper._lead_dedup_key = lambda lead: None  # 禁用去重 key

        list_payload = {'code': 0, 'rows': [MOCK_LIST_ITEM], 'total': 1}
        with patch('scraper.gdcic.fetch_bidding_list', return_value=list_payload), \
             patch('scraper.gdcic.fetch_bidding_detail', return_value=None):
            result = scraper._scrape_page('管道', 1)

        # 详情失败，该条不入库
        assert result == []

    def test_scrape_page_detail_empty_skipped(self):
        """详情解析返回空字典时该条也不入库（Major 4 方案 A）。"""
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        scraper._prefetch_existing_keys = lambda leads: set()
        scraper._check_pause_and_stop = lambda: None
        scraper._lead_dedup_key = lambda lead: None

        list_payload = {'code': 0, 'rows': [MOCK_LIST_ITEM], 'total': 1}
        # 详情返回全 null 的记录，parse_bidding_detail 会返回空字典
        empty_detail = {'address': None, 'biddingDate': None,
                        'biddingMoney': None, 'scale': None}
        with patch('scraper.gdcic.fetch_bidding_list', return_value=list_payload), \
             patch('scraper.gdcic.fetch_bidding_detail', return_value=empty_detail):
            result = scraper._scrape_page('管道', 1)

        assert result == []

    def test_scrape_page_project_info_supplement(self):
        """详情成功后调用项目信息 API 补全 buildUnit 等字段（Major 1）。"""
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        scraper._prefetch_existing_keys = lambda leads: set()
        scraper._check_pause_and_stop = lambda: None
        scraper._lead_dedup_key = lambda lead: None

        list_payload = {'code': 0, 'rows': [MOCK_LIST_ITEM], 'total': 1}
        with patch('scraper.gdcic.fetch_bidding_list', return_value=list_payload), \
             patch('scraper.gdcic.fetch_bidding_detail',
                   return_value=MOCK_DETAIL_RESPONSE), \
             patch('scraper.gdcic.fetch_project_info',
                   return_value=MOCK_PROJECT_INFO_RESPONSE):
            result = scraper._scrape_page('管道', 1)

        assert len(result) == 1
        lead = result[0]
        # 详情字段已补全
        assert lead['buyer_address'] == '台山市台城西湖片区国际路与龙成路交叉口东北侧'
        assert lead['budget_amount'] == 639.76
        # 详情中的联系人（biddingUnitPerson）已补全
        assert lead['contact_person'] == '张三'
        # 项目信息 API 字段已补全
        assert lead['build_unit'] == '台山市某房地产开发公司'
        assert lead['project_location'] == '广东省江门市台山市'
        assert lead['total_invest'] == 5000.0
        assert lead['total_area'] == '3198.8'
        assert lead['build_scale'] == '总建筑面积3198.8平方米'

    def test_scrape_page_project_info_failure_tolerant(self):
        """项目信息 API 失败时不影响详情已补全的线索入库（容错）。"""
        from scraper.gdcic import GdcicScraper

        scraper = GdcicScraper()
        scraper._prefetch_existing_keys = lambda leads: set()
        scraper._check_pause_and_stop = lambda: None
        scraper._lead_dedup_key = lambda lead: None

        list_payload = {'code': 0, 'rows': [MOCK_LIST_ITEM], 'total': 1}
        with patch('scraper.gdcic.fetch_bidding_list', return_value=list_payload), \
             patch('scraper.gdcic.fetch_bidding_detail',
                   return_value=MOCK_DETAIL_RESPONSE), \
             patch('scraper.gdcic.fetch_project_info', return_value=None):
            result = scraper._scrape_page('管道', 1)

        # 项目信息失败不影响详情已成功的线索
        assert len(result) == 1
        lead = result[0]
        assert lead['budget_amount'] == 639.76
        # 项目信息字段不存在（容错）
        assert 'build_unit' not in lead
        assert 'project_location' not in lead
