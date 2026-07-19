# -*- coding: utf-8 -*-
"""gdcic API 响应解析（将开放平台 JSON 转为 Lead dict）。

字段映射说明（API 字段 → Lead 字段）：
    projectName           → project_name       （项目名称）
    provinceBiddingCode   → bidding_number     （中标通知书编号，作为唯一编号）
    tenderType            → 存入 raw_data      （招标类型：施工/监理/设计等）
    tenderMode            → 存入 raw_data      （招标方式：公开招标/直接委托等）
    biddingUnit[].orgName → buyer_name         （中标单位/承包单位，建材获客目标客户）
    agentOrgName/agentUnit → agency_name       （招标代理机构）
    address               → buyer_address      （项目地址，详情字段）
    biddingMoney          → budget_amount      （中标金额，单位万元，详情字段）
    biddingDate           → publish_date       （招标日期，详情字段）
    scale                 → 存入 raw_data      （建设规模，详情字段）
    projectCode           → 存入 raw_data      （项目编号）

注意：
- 列表 API 返回的 address/biddingDate/biddingMoney/scale/agentUnit 均为 null，
  需调用详情 API 补全（parse_bidding_detail 处理）。
- biddingMoney 单位为万元，直接存入 budget_amount（Float），未做单位换算。
- region 固定为"广东省"（广东住建厅数据源）。
"""
import logging

from scraper.gdcic.utils import parse_gdcic_date

logger = logging.getLogger(__name__)

# 详情页 URL 模板（开放平台前端 SPA 路由）
_DETAIL_URL_TPL = 'https://skypt.gdcic.net/openplatform/#/web/project/bidding/detail?id={item_id}'

# 默认地域（广东住建厅数据均属广东省）
_DEFAULT_REGION = '广东省'

# 默认公告类型（开放平台招投标数据为中标结果）
_DEFAULT_ANNOUNCEMENT_TYPE = '中标公告'


def _text(value):
    """文本清理辅助函数：str() 防御 + strip()。

    替换所有 `(item.get('xxx') or '').strip()` 模式，避免非字符串类型
    （如 int/None）触发 AttributeError。
    """
    return str(value or '').strip()


def _join_org_names(org_list):
    """从组织列表中拼接 orgName，多个用逗号分隔。

    Args:
        org_list: [{"orgName": "...", "orgCode": "..."}, ...] 或 None

    Returns:
        str: 拼接后的名称字符串，无数据返回空字符串
    """
    if not org_list or not isinstance(org_list, list):
        return ''
    names = []
    for org in org_list:
        if isinstance(org, dict):
            name = _text(org.get('orgName'))
            if name:
                names.append(name)
    return ','.join(names)


def _join_org_codes(org_list):
    """从组织列表中拼接 orgCode，多个用逗号分隔。"""
    if not org_list or not isinstance(org_list, list):
        return ''
    codes = []
    for org in org_list:
        if isinstance(org, dict):
            code = _text(org.get('orgCode'))
            if code:
                codes.append(code)
    return ','.join(codes)


def _parse_bidding_persons(person_list):
    """解析 biddingUnitPerson 数组，提取联系人与电话。

    真实 API 数据结构（详情 API 中非空，列表 API 中通常为空数组）：
        [{"name": "李晓静", "orgName": "...", "orgCode": "...",
          "post": "项目经理", ...}, ...]

    字段映射：
        name / personName  → contact_person（多个用逗号拼接）
        phone / mobile / tel → phone（多个用逗号拼接，真实数据中通常无此字段）

    Args:
        person_list: biddingUnitPerson 数组或 None

    Returns:
        (contact_person, phone): 均为 str，无数据返回 ('', '')
    """
    if not person_list or not isinstance(person_list, list):
        return '', ''
    names = []
    phones = []
    for person in person_list:
        if not isinstance(person, dict):
            continue
        # 联系人姓名：兼容 name / personName 两种字段名
        name = _text(person.get('name')) or _text(person.get('personName'))
        if name:
            names.append(name)
        # 电话：兼容 phone / mobile / tel 三种字段名（真实 API 暂未提供）
        phone = (_text(person.get('phone'))
                 or _text(person.get('mobile'))
                 or _text(person.get('tel')))
        if phone:
            phones.append(phone)
    return ','.join(names), ','.join(phones)


def _parse_money(money_str):
    """解析中标金额字符串为 float。

    API 返回如 "639.76"（单位万元），转为 float。

    Returns:
        float or None
    """
    if not money_str:
        return None
    try:
        return float(str(money_str).strip())
    except (ValueError, TypeError):
        logger.debug('[gdcic] 金额解析失败: %s', money_str)
        return None


def parse_bidding_list_item(item):
    """将招投标列表 API 返回的单条数据转为 Lead dict。

    列表项中 address/biddingDate/biddingMoney/scale/agentUnit/biddingUnitPerson
    通常为 null 或空数组，需后续调用详情 API 补全（parse_bidding_detail）。

    Args:
        item: API 返回 rows 数组中的一个元素

    Returns:
        dict: Lead 字段字典（仅含非空字段），包含 _bidding_id 供详情调用使用
    """
    if not isinstance(item, dict):
        return {}

    item_id = _text(item.get('id'))
    project_name = _text(item.get('projectName'))

    # 无项目名称视为无效记录，直接返回空字典
    if not project_name:
        return {}

    lead = {
        'project_name': project_name[:500],
        'bidding_number': _text(item.get('provinceBiddingCode'))[:100],
        'announcement_type': _DEFAULT_ANNOUNCEMENT_TYPE,
        'region': _DEFAULT_REGION,
        'source_url': _DETAIL_URL_TPL.format(item_id=item_id) if item_id else '',
        # 临时字段：供 _scrape_page 调用详情 API 后 pop 掉
        '_bidding_id': item_id,
    }

    # 项目 ID 存入 raw_data（与 projectCode 区分，用于项目信息 API 查询）
    project_id = _text(item.get('projectId'))
    if project_id:
        lead['project_id'] = project_id

    # 中标单位（承包单位）→ buyer_name（建材获客目标客户）
    bidding_units = item.get('biddingUnit') or []
    buyer_name = _join_org_names(bidding_units)
    if buyer_name:
        lead['buyer_name'] = buyer_name[:200]
    # 中标单位代码存入 raw_data
    buyer_codes = _join_org_codes(bidding_units)
    if buyer_codes:
        lead['bidding_unit_codes'] = buyer_codes

    # 招标代理机构
    agency_name = _text(item.get('agentOrgName'))
    if agency_name:
        lead['agency_name'] = agency_name[:200]

    # 招标类型/方式存入 raw_data
    tender_type = _text(item.get('tenderType'))
    if tender_type:
        lead['tender_type'] = tender_type
    tender_mode = _text(item.get('tenderMode'))
    if tender_mode:
        lead['tender_mode'] = tender_mode

    # 项目编号存入 raw_data
    project_code = _text(item.get('projectCode'))
    if project_code:
        lead['project_code'] = project_code

    # 数据级别存入 raw_data
    data_level = _text(item.get('dataLevel'))
    if data_level:
        lead['data_level'] = data_level

    # biddingUnitPerson 联系人/电话（列表中通常为空，详情中可能有）。
    # 此处做防御性解析，非空时映射到 contact_person / phone。
    persons = item.get('biddingUnitPerson') or []
    contact_person, phone = _parse_bidding_persons(persons)
    if contact_person:
        lead['contact_person'] = contact_person[:50]
    if phone:
        lead['phone'] = phone[:50]

    # 过滤空值（保留 _bidding_id 即使为空，便于后续 pop）
    return {k: v for k, v in lead.items() if v not in (None, '') or k == '_bidding_id'}


def parse_bidding_detail(detail):
    """解析招投标详情 API 返回的数据，提取列表中为 null 的补充字段。

    Args:
        detail: 详情 API 返回的单条记录 dict

    Returns:
        dict: 补充字段字典（address/biddingDate/biddingMoney/scale/agentUnit/
              biddingUnitPerson 等）
    """
    if not isinstance(detail, dict):
        return {}

    result = {}

    # 项目地址
    address = _text(detail.get('address'))
    if address:
        result['buyer_address'] = address[:300]

    # 招标日期
    bidding_date_str = _text(detail.get('biddingDate'))
    if bidding_date_str:
        date_obj, time_str = parse_gdcic_date(bidding_date_str)
        if date_obj:
            result['publish_date'] = date_obj
            if time_str:
                result['publish_time'] = time_str

    # 中标金额（单位万元）
    money = _parse_money(detail.get('biddingMoney'))
    if money is not None:
        result['budget_amount'] = money

    # 建设规模存入 raw_data
    scale = _text(detail.get('scale'))
    if scale:
        result['scale'] = scale

    # 招标代理机构（详情中的 agentUnit 数组优先于列表中的 agentOrgName）
    agent_units = detail.get('agentUnit') or []
    agency_name = _join_org_names(agent_units)
    if agency_name:
        result['agency_name'] = agency_name[:200]
    elif _text(detail.get('agentOrgName')):
        result['agency_name'] = _text(detail.get('agentOrgName'))[:200]
    # 代理机构代码（与 bidding_unit_codes 对称）存入 raw_data
    agent_codes = _join_org_codes(agent_units)
    if agent_codes:
        result['agent_unit_codes'] = agent_codes

    # 详情中可能补全的中标单位（如果列表中为空），直接赋值覆盖
    bidding_units = detail.get('biddingUnit') or []
    buyer_name = _join_org_names(bidding_units)
    if buyer_name:
        result['buyer_name'] = buyer_name[:200]
    buyer_codes = _join_org_codes(bidding_units)
    if buyer_codes:
        result['bidding_unit_codes'] = buyer_codes

    # biddingUnitPerson 联系人/电话（详情 API 中通常非空，列表中为空数组）
    persons = detail.get('biddingUnitPerson') or []
    contact_person, phone = _parse_bidding_persons(persons)
    if contact_person:
        result['contact_person'] = contact_person[:50]
    if phone:
        result['phone'] = phone[:50]

    return result


def parse_project_info(info):
    """解析项目信息 API 返回的数据，补全建设单位/总投资/项目所在地等字段。

    真实 API 字段名（已用真实接口确认）：
        province / city / division  → 项目所在地（省/市/区）
        buildUnit                   → 建设单位
        totalInvestment             → 总投资（万元）
        totalArea                   → 总面积
        scale                       → 建设规模

    为兼容字段名可能的变化，同时尝试旧字段名（provinceName/cityName/
    districtName/totalInvest/buildScale）作为回退。

    Args:
        info: 项目信息 API 返回的记录 dict（字段在顶层，无 code/data 包装）

    Returns:
        dict: 补充字段字典（project_location/build_unit/total_invest/
              total_area/build_scale）
    """
    if not isinstance(info, dict):
        return {}

    result = {}

    # 项目所在地（省/市/区拼接），兼容 province/provinceName 两种字段名
    province = _text(info.get('province')) or _text(info.get('provinceName'))
    city = _text(info.get('city')) or _text(info.get('cityName'))
    district = _text(info.get('division')) or _text(info.get('districtName'))
    parts = [p for p in (province, city, district) if p]
    if parts:
        result['project_location'] = ''.join(parts)

    # 建设单位（项目信息中的建设单位，非中标单位）
    # 真实 API 中 buildUnit 是组织数组（含 orgName/orgCode），与 biddingUnit 结构一致；
    # 兼容旧版可能返回字符串的情况
    build_unit_raw = info.get('buildUnit')
    if isinstance(build_unit_raw, list):
        build_unit = _join_org_names(build_unit_raw)
        build_unit_codes = _join_org_codes(build_unit_raw)
        if build_unit_codes:
            result['build_unit_codes'] = build_unit_codes
    else:
        build_unit = _text(build_unit_raw)
    if build_unit:
        result['build_unit'] = build_unit[:200]

    # 总投资，兼容 totalInvestment/totalInvest 两种字段名
    total_invest = _parse_money(info.get('totalInvestment'))
    if total_invest is None:
        total_invest = _parse_money(info.get('totalInvest'))
    if total_invest is not None:
        result['total_invest'] = total_invest

    # 总面积
    total_area = _text(info.get('totalArea'))
    if total_area:
        result['total_area'] = total_area

    # 建设规模，兼容 scale/buildScale 两种字段名
    build_scale = _text(info.get('scale')) or _text(info.get('buildScale'))
    if build_scale:
        result['build_scale'] = build_scale

    return result
