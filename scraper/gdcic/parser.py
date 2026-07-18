# -*- coding: utf-8 -*-
"""gdcic 数据解析：API JSON 解析 + DOM HTML 解析 → Lead dict。

支持两种解析模式：
1. API JSON 解析（如果成功发现并直调 API）
2. DOM 解析（如果必须从 Playwright 渲染页面提取）
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.gdcic.utils import clean_gdcic_text, parse_gdcic_date, extract_gdcic_phone

logger = logging.getLogger(__name__)

# API JSON 字段映射：常见键名 → Lead 字段名
# 由于 gdcic API 结构未知，列出多种可能的键名以提高兼容性
_API_FIELD_MAP = {
    'project_name': [
        'projectName', 'project_name', 'name', 'title', 'xmcName',
        'xmmc', 'xmmcName', 'gcName', 'gcmc', 'projectTitle',
    ],
    'bidding_number': [
        'biddingNumber', 'bidding_number', 'projectCode', 'project_code',
        'xmbh', 'gcbh', 'code', 'no', 'number',
    ],
    'announcement_type': [
        'announcementType', 'type', 'typeName', 'ggType', 'gglx',
        'noticeType', 'category', 'categoryName',
    ],
    'buyer_name': [
        'buyerName', 'buyer_name', 'purchaser', 'purchaserName',
        'ownerName', 'owner', 'dwmc', 'jsdw', 'jsdwmc',
        'constructionUnit', 'unitName',
    ],
    'buyer_address': [
        'buyerAddress', 'address', 'buyer_address', 'dwAddress',
        'jsdwAddress', 'projectAddress',
    ],
    'region': [
        'region', 'area', 'city', 'areaName', 'cityName',
        'dq', 'dqmc', 'province', 'projectArea',
    ],
    'contact_person': [
        'contactPerson', 'contact', 'contactName', 'lxr',
        'lxrxm', 'contact_person',
    ],
    'phone': [
        'phone', 'telephone', 'tel', 'contactPhone', 'lxdh',
        'lxPhone', 'mobile', 'phone',
    ],
    'agency_name': [
        'agencyName', 'agency', 'agentName', 'dljg', 'dljgmc',
    ],
    'agency_phone': [
        'agencyPhone', 'agencyTel', 'dldh',
    ],
    'budget_amount': [
        'budgetAmount', 'budget', 'amount', 'ysje', 'ysAmount',
        'totalAmount', 'contractAmount',
    ],
    'publish_date': [
        'publishDate', 'publishTime', 'createTime', 'fbDate',
        'createDate', 'releaseDate', 'pubDate', 'date',
    ],
    'deadline': [
        'deadline', 'endTime', 'jzDate', 'expiryDate',
    ],
    'source_url': [
        'url', 'detailUrl', 'link', 'href', 'sourceUrl',
    ],
}


def parse_api_list(rows, base_url='https://www.gdcic.net'):
    """解析 API JSON 返回的原始数据列表。

    对每条记录尝试多种字段映射，兼容不同的 API 响应结构。

    Args:
        rows: API 返回的数据行列表（dict list）
        base_url: 基础 URL，用于拼接相对路径

    Returns:
        list[dict]: Lead dict 列表
    """
    if not rows:
        return []

    leads = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        lead = _parse_api_row(row, base_url)
        if lead and lead.get('project_name'):
            leads.append(lead)

    logger.info('[gdcic] API 解析: %d 行 → %d 条有效线索', len(rows), len(leads))
    return leads


def _parse_api_row(row, base_url):
    """解析单条 API 数据行。"""
    lead = {}

    for lead_field, api_keys in _API_FIELD_MAP.items():
        for key in api_keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                lead[lead_field] = str(value).strip()
                break

    # 日期字段特殊处理
    for date_field in ('publish_date', 'publish_time', 'deadline'):
        if date_field in lead:
            date_obj, time_str = parse_gdcic_date(lead[date_field])
            if date_obj:
                lead[date_field] = date_obj
                if time_str and date_field == 'publish_date':
                    lead['publish_time'] = time_str

    # source_url 补全
    if lead.get('source_url') and not lead['source_url'].startswith(('http://', 'https://')):
        lead['source_url'] = urljoin(base_url, lead['source_url'])

    # 从文本中提取电话（如果 phone 字段为空）
    if not lead.get('phone'):
        full_text = ' '.join(str(v) for v in row.values() if isinstance(v, str))
        phone = extract_gdcic_phone(full_text)
        if phone:
            lead['phone'] = phone

    return lead


def parse_dom_list(html, base_url='https://www.gdcic.net'):
    """解析 DOM 渲染页面 HTML，提取列表数据。

    尝试多种常见选择器以适配不同页面结构：
    1. Element UI 表格
    2. 常见列表容器
    3. 通用 fallback：所有含日期的链接

    Args:
        html: 页面 HTML 字符串
        base_url: 基础 URL

    Returns:
        list[dict]: Lead dict 列表
    """
    if not html:
        return []

    soup = _make_soup(html)
    results = []

    # 策略 1：Element UI / Vue 表格
    table_rows = soup.select(
        'table.el-table__body tbody tr, '
        'table tbody tr, '
        '.el-table__body-wrapper table tbody tr'
    )
    # 获取表头
    headers = _extract_table_headers(soup)

    for row in table_rows:
        lead = _parse_table_row(row, headers, base_url)
        if lead and lead.get('project_name'):
            results.append(lead)

    if results:
        logger.info('[gdcic] DOM 表格解析: %d 条', len(results))
        return results

    # 策略 2：列表容器
    list_items = soup.select(
        'ul.list li, ul.el-list li, div.list-item, '
        'div.el-card, div.result-item, div.info-item, '
        '.data-list .item, .list-container .item'
    )
    for item in list_items:
        lead = _parse_list_item(item, base_url)
        if lead and lead.get('project_name'):
            results.append(lead)

    if results:
        logger.info('[gdcic] DOM 列表解析: %d 条', len(results))
        return results

    # 策略 3：Fallback — 含日期的链接
    results = _fallback_parse_links(soup, base_url)
    logger.info('[gdcic] DOM Fallback 解析: %d 条', len(results))
    return results


def _make_soup(html):
    """创建 BeautifulSoup 对象。"""
    try:
        return BeautifulSoup(html, 'lxml')
    except Exception:
        return BeautifulSoup(html, 'html.parser')


def _extract_table_headers(soup):
    """提取表格表头文本列表。"""
    headers = []
    header_cells = soup.select(
        'table.el-table__header th, table thead th, '
        '.el-table__header-wrapper th'
    )
    for cell in header_cells:
        text = cell.get_text(strip=True)
        headers.append(text)
    return headers


def _parse_table_row(row, headers, base_url):
    """解析表格行，结合表头映射字段。"""
    cells = row.select('td')
    if not cells:
        return {}

    lead = {}
    cell_texts = []
    for cell in cells:
        cell_texts.append(clean_gdcic_text(cell.get_text()))

    # 如果有表头，按表头映射
    if headers:
        kv = {}
        for i, header in enumerate(headers):
            if i < len(cell_texts):
                kv[header] = cell_texts[i]

        lead = _map_kv_to_lead(kv, base_url)
    else:
        # 无表头时，尝试从文本内容推断
        full_text = ' | '.join(cell_texts)
        lead = _infer_lead_from_text(full_text, base_url)

    # 提取链接
    link = row.select_one('a[href]')
    if link:
        href = link.get('href', '')
        if href and not href.startswith(('javascript:', '#', 'mailto:')):
            lead['source_url'] = _resolve_url(href, base_url)
        if not lead.get('project_name'):
            lead['project_name'] = clean_gdcic_text(link.get_text())

    return lead


def _map_kv_to_lead(kv, base_url):
    """将表头键值对映射为 Lead dict。"""
    lead = {}

    # 表头关键词 → Lead 字段映射
    header_map = {
        'project_name': ['项目名称', '工程名称', '项目', '名称', '标题', '公告标题', '项目名'],
        'bidding_number': ['编号', '项目编号', '招标编号', '工程编号', '公告编号'],
        'announcement_type': ['类型', '公告类型', '类别', '分类'],
        'buyer_name': ['建设单位', '采购人', '采购单位', '招标人', '业主', '甲方', '单位'],
        'region': ['地区', '地域', '所在区域', '项目地区', '城市'],
        'budget_amount': ['金额', '预算', '预算金额', '合同金额', '中标金额'],
        'publish_date': ['日期', '发布日期', '发布时间', '公告日期', '发布日期', '时间'],
        'contact_person': ['联系人', '项目联系人'],
        'phone': ['电话', '联系电话', '联系方式'],
        'deadline': ['截止日期', '截止时间', '报名截止'],
    }

    for lead_field, header_keywords in header_map.items():
        for header_text, cell_text in kv.items():
            for kw in header_keywords:
                if kw in header_text:
                    lead[lead_field] = cell_text[:500]
                    break
            if lead_field in lead:
                break

    # 日期处理
    if 'publish_date' in lead:
        date_obj, time_str = parse_gdcic_date(lead['publish_date'])
        if date_obj:
            lead['publish_date'] = date_obj
            if time_str:
                lead['publish_time'] = time_str

    return lead


def _infer_lead_from_text(text, base_url):
    """从纯文本推断 Lead 字段。"""
    lead = {}

    # 提取项目名称（通常是最长的一段中文文本）
    # 简单策略：取前 200 字符作为项目名称
    parts = [p.strip() for p in text.split('|') if p.strip()]
    if parts:
        # 取最长的部分作为项目名称
        longest = max(parts, key=len)
        if len(longest) >= 4:
            lead['project_name'] = longest[:500]

    # 提取日期
    date_match = re.search(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', text)
    if date_match:
        date_obj, time_str = parse_gdcic_date(date_match.group(0))
        if date_obj:
            lead['publish_date'] = date_obj

    return lead


def _parse_list_item(item, base_url):
    """解析列表项（div/li）。"""
    lead = {}

    # 标题 + 链接
    title_tag = item.select_one('a[href], h3 a, h4 a, .title a, .name a')
    if title_tag:
        lead['project_name'] = clean_gdcic_text(title_tag.get_text())
        href = title_tag.get('href', '')
        if href and not href.startswith(('javascript:', '#', 'mailto:')):
            lead['source_url'] = _resolve_url(href, base_url)

    # 日期
    date_el = item.select_one('.date, .time, .pub-date, span[class*="date"]')
    if date_el:
        date_text = date_el.get_text(strip=True)
        date_obj, time_str = parse_gdcic_date(date_text)
        if date_obj:
            lead['publish_date'] = date_obj
            if time_str:
                lead['publish_time'] = time_str
    else:
        # 从文本中提取日期
        full_text = item.get_text()
        date_match = re.search(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', full_text)
        if date_match:
            date_obj, time_str = parse_gdcic_date(date_match.group(0))
            if date_obj:
                lead['publish_date'] = date_obj

    # 类型标签
    type_el = item.select_one('.type, .tag, .label, span[class*="type"]')
    if type_el:
        lead['announcement_type'] = clean_gdcic_text(type_el.get_text())[:50]

    return lead


def _fallback_parse_links(soup, base_url):
    """Fallback：从所有链接中提取含日期的条目。"""
    results = []
    date_pattern = re.compile(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}')

    for a_tag in soup.select('a[href]'):
        text = clean_gdcic_text(a_tag.get_text())
        if not text or len(text) < 5:
            continue

        href = a_tag.get('href', '')
        if not href or href in ('#', '/', 'javascript:void(0)'):
            continue

        # 检查父节点中是否有日期
        parent = a_tag.parent
        parent_text = parent.get_text() if parent else ''
        date_match = date_pattern.search(parent_text)

        if date_match:
            date_obj, time_str = parse_gdcic_date(date_match.group(0))
            lead = {
                'project_name': text[:500],
                'source_url': _resolve_url(href, base_url),
            }
            if date_obj:
                lead['publish_date'] = date_obj
            if time_str:
                lead['publish_time'] = time_str
            results.append(lead)

    return results


def _resolve_url(href, base_url):
    """将相对 URL 转为绝对 URL。"""
    if not href:
        return ''
    href = href.strip()
    if href.startswith(('http://', 'https://')):
        return href
    return urljoin(base_url, href)
