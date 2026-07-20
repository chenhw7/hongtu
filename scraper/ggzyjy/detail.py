# -*- coding: utf-8 -*-
"""ggzyjy 详情 API 调用 + richText HTML 解析。"""
import logging
import re

from bs4 import BeautifulSoup

from scraper.ggzyjy.utils import parse_budget, parse_phone, parse_richtext_fields

logger = logging.getLogger(__name__)

_DETAIL_URL = 'https://ygp.gdzwfw.gov.cn/ggzy-portal/center/apis/trading-notice/new/detail'

# keyTable 中的字段名 -> Lead 字段映射
_KEYTABLE_FIELD_MAP = {
    'TENDER_PROJECT_NAME': 'project_name',
    'BID_SECTION_NAME': '_bid_section',
    'PROJECT_CODE': 'bidding_number',
}

# richText 中的中文标签 -> Lead 字段映射
_RICHTEXT_LABEL_MAP = {
    '招标人': 'buyer_name',
    '采购人': 'buyer_name',
    '建设单位': 'buyer_name',
    '招标人联系地址': 'buyer_address',
    '招标人地址': 'buyer_address',
    '采购人地址': 'buyer_address',
    '招标人联系人': 'contact_person',
    '招标人联系电话': 'phone',
    '联系人': 'contact_person',
    '联系电话': 'phone',
    '招标代理机构': 'agency_name',
    '代理机构': 'agency_name',
    '招标代理联系地址': '_agency_address',
    '招标代理联系电话': 'agency_phone',
    '代理机构联系电话': 'agency_phone',
    '最高投标限价': '_budget_text',
    '预算金额': '_budget_text',
    '投标文件递交截止时间': '_deadline_text',
    '投标截止时间': '_deadline_text',
    '开标时间': '_deadline_text',
    '投资项目代码': 'bidding_number',
    '招标项目编号': 'bidding_number',
}


def fetch_detail(scraper, notice_id, project_code, site_code, trading_type='A',
                 trading_process=''):
    """获取并解析粤公平详情页（GET JSON 接口 + richText HTML 解析）。

    Args:
        scraper: GgzyjyScraper 实例
        notice_id: 公告 ID
        project_code: 项目编码
        site_code: 地区编码
        trading_type: 交易类型（"A"=工程建设, "D"=政府采购, "R"=其他）
        trading_process: 交易环节 ID（搜索接口返回的 tradingProcess 字段，用作 nodeId）

    Returns:
        dict: 补充字段（联系人、电话、预算、截止日期、附件、原始 HTML 等），
              请求失败返回空 dict
    """
    if not notice_id:
        return {}

    # bizCode 为 noticeId 前 4 位（API 必需参数）
    biz_code = notice_id[:4] if len(notice_id) >= 4 else ''
    # nodeId 使用搜索接口返回的 tradingProcess
    node_id = trading_process or ''

    # 如果 tradingProcess 含字母（如 3C14），它实际上是 bizCode 而非 nodeId
    # 纯数字的 tradingProcess（如 3111, 3822）可直接用作 nodeId
    if node_id and not node_id.isdigit():
        biz_code = node_id  # tradingProcess 就是 bizCode
        node_id = _fetch_node_id(scraper, notice_id, project_code, site_code,
                                 biz_code, trading_type)

    params = {
        'nodeId': node_id,
        'version': 'v3',
        'tradingType': trading_type,
        'noticeId': notice_id,
        'bizCode': biz_code,
        'projectCode': project_code,
        'siteCode': site_code,
    }

    response = scraper.fetch(_DETAIL_URL, params=params,
                             extra_headers={'Accept': 'application/json'})
    if response is None:
        return {}

    try:
        payload = response.json()
    except ValueError:
        logger.warning('[ggzyjy] 详情接口返回非 JSON: %s', response.text[:200])
        return {}

    if payload.get('errcode') != 0 and not payload.get('data'):
        logger.warning('[ggzyjy] 详情接口返回异常: %s', payload.get('errmsg'))
        return {}

    data = payload.get('data') or payload
    detail = {}

    # 1) 解析 tradingNoticeColumnModelList
    column_list = data.get('tradingNoticeColumnModelList') or []
    for column in column_list:
        # API 返回 viewStyle 而非 type，数据在不同字段中
        col_type = column.get('viewStyle') or column.get('type') or ''

        if col_type == 'keyTable':
            # 新版 API: multiKeyValueTableList (list of list of dict)
            kv_list = column.get('multiKeyValueTableList')
            if kv_list:
                _parse_key_table(kv_list, detail)
            else:
                col_data = column.get('data')
                if col_data:
                    _parse_key_table(col_data, detail)
        elif col_type == 'richText':
            # 新版 API: richtext 字段
            rt_data = column.get('richtext') or column.get('data')
            if rt_data:
                _parse_rich_text(rt_data, detail)

        # 提取附件（可能在任意 column 中）
        file_list = column.get('noticeFileBOList')
        if file_list:
            attachments = _extract_attachments(
                {'noticeFileBOList': file_list}, notice_id, site_code)
            if attachments:
                detail.setdefault('attachments', []).extend(attachments)

    # 2) 提取附件列表（兼容旧版顶层 noticeFileBOList）
    attachments = _extract_attachments(data, notice_id, site_code)
    if attachments:
        detail.setdefault('attachments', []).extend(attachments)

    # 3) 保存原始 JSON 文本作为快照（richText 内容更有参考价值）
    rich_text_html = _collect_richtext_html(column_list)
    if rich_text_html:
        detail['_raw_html'] = rich_text_html

    # 过滤空值（不输出空字符串，避免覆盖列表页已有的字段）
    return {k: v for k, v in detail.items() if v not in (None, '')}


_NODELIST_URL = ('https://ygp.gdzwfw.gov.cn/ggzy-portal/center/apis/'
                 'trading-notice/new/nodeList')


def _fetch_node_id(scraper, notice_id, project_code, site_code, biz_code,
                   trading_type):
    """通过 nodeList API 获取真正的 nodeId。

    当搜索接口返回的 tradingProcess 是 4 位 hex（即 bizCode）时，
    需要额外请求 nodeList 接口获取交易环节 ID。

    Returns:
        str: nodeId，获取失败返回空字符串
    """
    params = {
        'noticeId': notice_id,
        'projectCode': project_code,
        'siteCode': site_code,
        'bizCode': biz_code,
        'tradingType': trading_type,
    }
    response = scraper.fetch(_NODELIST_URL, params=params,
                             extra_headers={'Accept': 'application/json'})
    if response is None:
        return ''
    try:
        payload = response.json()
    except ValueError:
        return ''
    if payload.get('errcode') != 0:
        return ''
    nodes = payload.get('data') or []
    # 优先找有数据的节点（dataCount > 0 且 noticeId 匹配）
    for node in nodes:
        if (node.get('noticeId') == notice_id and node.get('nodeId')):
            return str(node['nodeId'])
    # 回退：取第一个 dataCount > 0 的节点
    for node in nodes:
        if node.get('dataCount', 0) > 0 and node.get('nodeId'):
            return str(node['nodeId'])
    return ''

def _parse_key_table(key_table_data, detail):
    """解析 keyTable 类型的结构化键值对数据。

    支持两种格式：
    - 新版 API: multiKeyValueTableList = [[{code, key, value}, ...], ...]
    - 旧版 API: data = [{key/fieldName, value/fieldValue}, ...] 或 dict

    Args:
        key_table_data: keyTable 的数据字段
        detail: 写入目标 dict
    """
    if isinstance(key_table_data, list):
        for item in key_table_data:
            # 新版嵌套列表: [[{...}, {...}], ...]
            if isinstance(item, list):
                for row in item:
                    if isinstance(row, dict):
                        _extract_kv_row(row, detail)
            elif isinstance(item, dict):
                _extract_kv_row(item, detail)
    elif isinstance(key_table_data, dict):
        for key, value in key_table_data.items():
            if key and value:
                mapped = _KEYTABLE_FIELD_MAP.get(key)
                if mapped and not mapped.startswith('_'):
                    if not detail.get(mapped):
                        detail[mapped] = str(value)[:500]


def _extract_kv_row(row, detail):
    """从单行键值对中提取字段。

    新版 API 行格式: {code: 'TENDER_PROJECT_NAME', key: '招标项目名称', value: '...'}
    旧版 API 行格式: {key: '...', value: '...'} 或 {fieldName: '...', fieldValue: '...'}
    """
    # 优先用 code 字段匹配（新版 API）
    code = (row.get('code') or '').strip()
    key = (row.get('key') or row.get('fieldName') or '').strip()
    value = (row.get('value') or row.get('fieldValue') or '').strip()
    if not value:
        return
    # 先尝试 code 匹配，再尝试 key 匹配
    mapped = _KEYTABLE_FIELD_MAP.get(code) or _KEYTABLE_FIELD_MAP.get(key)
    if mapped and not mapped.startswith('_'):
        if not detail.get(mapped):
            detail[mapped] = value[:500]


def _parse_rich_text(rich_text_data, detail):
    """解析 richText 类型的 HTML 内容。

    从 HTML 表格中提取招标人、联系人、电话、预算金额、截止日期等字段。

    Args:
        rich_text_data: richText 的 data 字段（HTML 字符串）
        detail: 写入目标 dict
    """
    html_text = rich_text_data if isinstance(rich_text_data, str) else str(rich_text_data)
    if not html_text or len(html_text) < 10:
        return

    fields = parse_richtext_fields(html_text)
    if not fields:
        return

    for label, value in fields.items():
        mapped = _RICHTEXT_LABEL_MAP.get(label)
        if not mapped:
            continue
        if mapped.startswith('_'):
            # 特殊处理字段
            if mapped == '_budget_text':
                budget = parse_budget(value)
                if budget is not None and not detail.get('budget_amount'):
                    detail['budget_amount'] = budget
            elif mapped == '_deadline_text':
                deadline = _parse_deadline_text(value)
                if deadline and not detail.get('deadline'):
                    detail['deadline'] = deadline
            elif mapped == '_agency_address':
                if not detail.get('agency_address'):
                    detail['_agency_address'] = value[:300]
        else:
            if not detail.get(mapped):
                detail[mapped] = value[:500]

    # 电话字段：尝试从相关标签中提取
    if not detail.get('phone'):
        for label in ('招标人联系电话', '招标人电话', '联系电话', '联系方式', '电话'):
            phone_val = fields.get(label, '')
            phone = parse_phone(phone_val)
            if phone:
                detail['phone'] = phone[:50]
                break

    # 联系人字段
    if not detail.get('contact_person'):
        for label in ('招标人联系人', '招标人委托代理人', '联系人', '项目联系人'):
            val = fields.get(label, '')
            if val:
                detail['contact_person'] = val[:50]
                break


def _parse_deadline_text(text):
    """从文本中解析截止日期。

    支持格式：
        "2026-07-20 09:30"
        "2026年07月20日 09:30"
        "2026/07/20 09:30:00"
    """
    if not text:
        return None
    text = str(text).strip()
    from scraper.utils import parse_date
    # 先尝试提取日期部分
    m = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
    if m:
        return parse_date(m.group(1))
    return None


def _extract_attachments(data, notice_id, site_code):
    """从详情数据中提取附件列表。

    Args:
        data: 详情接口返回的 data dict
        notice_id: 公告 ID
        site_code: 地区编码

    Returns:
        list[dict]: 附件列表 [{'name': ..., 'url': ...}]
    """
    attachments = []
    file_list = data.get('noticeFileBOList') or []
    for f in file_list:
        file_name = (f.get('fileName') or f.get('name') or '').strip()
        row_guid = (f.get('rowGuid') or f.get('fileId') or '').strip()
        file_url = (f.get('fileUrl') or f.get('url') or '').strip()

        if not file_url and row_guid:
            # 构建附件下载 URL
            file_url = (f'https://ygp.gdzwfw.gov.cn/ggzy-portal/center/apis/'
                       f'file/download?rowGuid={row_guid}')

        if file_url:
            attachments.append({
                'name': (file_name or 'attachment')[:200],
                'url': file_url[:500],
            })
    return attachments


def _collect_richtext_html(column_list):
    """收集所有 richText 列的 HTML 内容，拼接为完整的原始文本快照。"""
    parts = []
    for column in column_list:
        col_type = column.get('viewStyle') or column.get('type') or ''
        if col_type == 'richText':
            rt = column.get('richtext') or column.get('data')
            if rt:
                parts.append(str(rt))
    return '\n'.join(parts) if parts else None
