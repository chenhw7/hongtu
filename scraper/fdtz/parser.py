# -*- coding: utf-8 -*-
"""fdtz 字段映射：将 API 返回的列表/详情数据转换为 Lead dict。

不同分类（备案/核准/审批）字段名存在差异，此处统一处理。
"""
import logging

from scraper.fdtz.utils import parse_fdtz_date, parse_investment

logger = logging.getLogger(__name__)

# 各分类对应的 flag 值（列表接口用）
CATEGORY_FLAGS = {
    'ba': '1',      # 备案项目，flag=1 表示公开
    'hz_gs': '9',   # 核准项目公示
    'hz_gg': '10',  # 核准项目公告
    'sp_gs': '6',   # 审批项目公示
    'sp_gg': '7',   # 审批项目公告
    'jn': '13',     # 节能审查公告
}

# 分类中文标签（用于日志/进度展示）
CATEGORY_LABELS = {
    'ba': '备案项目',
    'hz_gs': '核准公示',
    'hz_gg': '核准公告',
    'sp_gs': '审批公示',
    'sp_gg': '审批公告',
    'jn': '节能审查',
}

# 详情接口端点映射
DETAIL_ENDPOINTS = {
    'ba': 'selectBaProjectInfo',
    'hz_gs': 'getHzgsInfoById',
    'hz_gg': 'getHzggInfoById',
    'sp_gs': 'getSpgsInfoById',
    'sp_gg': 'getSpggInfoById',
}

# 详情接口 ID 参数名映射
DETAIL_ID_PARAMS = {
    'ba': 'baId',
    'hz_gs': 'id',
    'hz_gg': 'id',
    'sp_gs': 'id',
    'sp_gg': 'id',
}

# 详情页 URL 模板（发改委平台前端 SPA 路由）
_DETAIL_URL_TPL = 'https://tzxm.gd.gov.cn/tzxmspweb/home/informationPublicity/{category}?{id_param}={item_id}'


def _get_item_id(item, category):
    """从列表项提取主键 ID，各分类字段名不同。"""
    if category == 'ba':
        return (item.get('baId') or item.get('id') or '').strip()
    else:
        return (item.get('id') or item.get('baId') or '').strip()


def _get_field(item, *field_names, default=''):
    """按优先级从 item 中取第一个非空字段。"""
    for name in field_names:
        val = item.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def parse_list_item(item, category):
    """将列表接口返回的单条数据转换为 Lead dict。

    Args:
        item: 列表 API 返回的单条数据 dict
        category: 分类标识（ba/hz_gs/hz_gg/sp_gs/sp_gg/jn）

    Returns:
        dict: Lead 字段字典，含必要的 _item_id 和 _category 元数据
    """
    item_id = _get_item_id(item, category)

    # 项目编号：备案用 proofCode，核准/审批用 projectCode
    bidding_number = _get_field(item, 'projectCode', 'proofCode')

    # 项目名称
    project_name = _get_field(item, 'projectName', 'pname')[:500]

    # 建设单位：备案用 applyOrgan，核准/审批用 buildOrgan
    buyer_name = _get_field(item, 'applyOrgan', 'buildOrgan', 'applyUnit')[:200]

    # 地域
    region = _get_field(item, 'place', 'city', 'regionName')[:50]

    # 公告类型
    announcement_type = CATEGORY_LABELS.get(category, category)

    lead = {
        'project_name': project_name,
        'bidding_number': bidding_number[:100] if bidding_number else '',
        'announcement_type': announcement_type,
        'buyer_name': buyer_name,
        'region': region,
    }

    # 发布日期：finishDate / createDate / publishDate
    date_val = _get_field(item, 'finishDate', 'createDate', 'publishDate', 'auditDate')
    if date_val:
        publish_date, publish_time = parse_fdtz_date(date_val)
        if publish_date:
            lead['publish_date'] = publish_date
        if publish_time:
            lead['publish_time'] = publish_time

    # 总投资（万元 → 元）
    total_invest = item.get('totalInvest') or item.get('invest') or item.get('totalInvestment')
    budget = parse_investment(total_invest)
    if budget:
        lead['budget_amount'] = budget

    # 详情 URL
    if item_id:
        lead['source_url'] = _DETAIL_URL_TPL.format(
            category=category,
            id_param=DETAIL_ID_PARAMS.get(category, 'id'),
            item_id=item_id,
        )[:500]

    # 元数据（详情接口用，save_leads 前由调用方 pop）
    lead['_item_id'] = item_id
    lead['_category'] = category

    # 过滤空值（保留 0 金额）
    return {k: v for k, v in lead.items() if v not in (None, '') or k == 'budget_amount'}


def parse_detail(detail_data, category):
    """将详情接口返回的数据解析为补充字段 dict。

    详情页通常包含更完整的项目信息，用于补充列表页缺失字段。

    Args:
        detail_data: 详情 API 返回的 JSON dict
        category: 分类标识

    Returns:
        dict: 补充字段字典
    """
    if not detail_data:
        return {}

    # 详情可能嵌套在 data / info 字段内
    data = detail_data.get('data') or detail_data.get('info') or detail_data

    extra = {}

    # 补充项目编号
    bidding_number = _get_field(data, 'projectCode', 'proofCode')
    if bidding_number:
        extra['bidding_number'] = bidding_number[:100]

    # 补充项目名称
    project_name = _get_field(data, 'projectName', 'pname')
    if project_name:
        extra['project_name'] = project_name[:500]

    # 补充建设单位
    buyer_name = _get_field(data, 'applyOrgan', 'buildOrgan', 'applyUnit', 'owner')
    if buyer_name:
        extra['buyer_name'] = buyer_name[:200]

    # 补充地域
    region = _get_field(data, 'place', 'city', 'regionName', 'county')
    if region:
        extra['region'] = region[:50]

    # 补充发布日期
    date_val = _get_field(data, 'finishDate', 'createDate', 'publishDate', 'auditDate')
    if date_val:
        publish_date, publish_time = parse_fdtz_date(date_val)
        if publish_date:
            extra['publish_date'] = publish_date
        if publish_time:
            extra['publish_time'] = publish_time

    # 补充投资金额
    total_invest = data.get('totalInvest') or data.get('invest') or data.get('totalInvestment')
    budget = parse_investment(total_invest)
    if budget:
        extra['budget_amount'] = budget

    # 批复文号（审批类特有）
    approval_no = _get_field(data, 'approvalNo', 'docNo', 'approvalCode')
    if approval_no:
        extra['approval_no'] = approval_no[:100]

    # 建设规模描述（存为 raw_data 字段）
    description = _get_field(data, 'buildContent', 'projectDesc', 'content')
    if description:
        extra['description'] = description[:2000]

    return extra
