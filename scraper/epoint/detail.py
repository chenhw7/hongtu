# -*- coding: utf-8 -*-
"""EpointWebBuilder SSR HTML 详情页解析。

EpointWebBuilder 平台的详情页是服务端渲染的 HTML 页面，通常包含结构化表格
（项目登记信息、招标人、预算等）。本模块使用 BeautifulSoup 提取关键字段。
"""
import logging

from bs4 import BeautifulSoup

from scraper.epoint.utils import parse_budget, parse_phone, parse_epoint_date

logger = logging.getLogger(__name__)

# SSR HTML 表格中的中文标签 -> Lead 字段映射
_LABEL_MAP = {
    '项目名称': 'project_name',
    '工程名称': 'project_name',
    '项目编号': 'bidding_number',
    '投资项目代码': 'bidding_number',
    '招标项目编号': 'bidding_number',
    '项目代码': 'bidding_number',
    '审批机关': '_approval_authority',
    '项目法人': '_project_owner',
    '建设单位': 'buyer_name',
    '招标人': 'buyer_name',
    '采购人': 'buyer_name',
    '招标人地址': 'buyer_address',
    '招标人联系地址': 'buyer_address',
    '招标人联系电话': 'phone',
    '招标人联系人': 'contact_person',
    '联系人': 'contact_person',
    '联系电话': 'phone',
    '招标代理机构': 'agency_name',
    '代理机构': 'agency_name',
    '代理机构联系电话': 'agency_phone',
    '代理机构地址': '_agency_address',
    '投资金额': '_budget_text',
    '预算金额': '_budget_text',
    '最高投标限价': '_budget_text',
    '合同估算价': '_budget_text',
    '项目预算': '_budget_text',
    '投标文件递交截止时间': '_deadline_text',
    '投标截止时间': '_deadline_text',
    '开标时间': '_deadline_text',
    '建设地点': '_build_location',
    '建设规模': '_build_scale',
    '资金来源': '_fund_source',
}


def fetch_detail(scraper, detail_path):
    """获取并解析 SSR HTML 详情页。

    Args:
        scraper: EpointBaseScraper 实例
        detail_path: 详情页相对路径（如 /jyxxgk/002001/002001001/.../xxx.html）

    Returns:
        dict: 补充字段（联系人、电话、预算等），请求失败返回空 dict
    """
    if not detail_path:
        return {}

    detail_url = scraper.base_url.rstrip('/') + detail_path
    html_text, soup = scraper.fetch_html(detail_url)
    if soup is None:
        return {}

    detail = {}

    # 1) 从 HTML 表格中提取结构化键值对
    _parse_tables(soup, detail)

    # 2) 兜底：从正文段落中提取 "标签：值" 形式
    _parse_text_labels(soup, detail)

    # 3) 提取附件
    attachments = _extract_attachments(soup, scraper.base_url, detail_path)
    if attachments:
        detail['attachments'] = attachments

    # 4) 保存原始 HTML 作为快照
    if html_text:
        detail['_raw_html'] = html_text

    # 过滤空值
    return {k: v for k, v in detail.items() if v not in (None, '')}


def _parse_tables(soup, detail):
    """从 HTML 表格中提取键值对。

    支持两种格式：
    - 2列：<tr><td>标签</td><td>值</td></tr>
    - 4列：<tr><td>标签</td><td>值</td><td>标签</td><td>值</td></tr>
    """
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            # 2列格式
            if len(cells) >= 2:
                _extract_cell_pair(cells[0], cells[1], detail)
            # 4列格式
            if len(cells) >= 4:
                _extract_cell_pair(cells[2], cells[3], detail)


def _extract_cell_pair(label_cell, value_cell, detail):
    """从一对表格单元格中提取字段。"""
    label = label_cell.get_text(strip=True).rstrip('：:').strip()
    value = value_cell.get_text(strip=True)
    if not label or not value:
        return

    mapped = _LABEL_MAP.get(label)
    if not mapped:
        return

    if mapped.startswith('_'):
        # 特殊处理字段
        if mapped == '_budget_text':
            budget = parse_budget(value)
            if budget is not None and not detail.get('budget_amount'):
                detail['budget_amount'] = budget
        elif mapped == '_deadline_text':
            deadline_date, _ = parse_epoint_date(value)
            if deadline_date and not detail.get('deadline'):
                detail['deadline'] = deadline_date
        elif mapped == '_agency_address':
            if not detail.get('agency_address'):
                detail[mapped] = value[:300]
    else:
        if not detail.get(mapped):
            detail[mapped] = value[:500]

    # 电话字段兜底
    if not detail.get('phone') and label in ('联系电话', '招标人联系电话', '联系方式'):
        phone = parse_phone(value)
        if phone:
            detail['phone'] = phone[:50]


def _parse_text_labels(soup, detail):
    """从正文段落中提取 '标签：值' 形式的键值对（兜底方案）。"""
    import re

    text = soup.get_text('\n', strip=True)
    for line in text.split('\n'):
        m = re.match(r'^[  ]*([^：:]{2,20})[：:]\s*(.+)$', line.strip())
        if m:
            label = m.group(1).strip()
            value = m.group(2).strip()
            if label and value:
                mapped = _LABEL_MAP.get(label)
                if mapped and not mapped.startswith('_') and not detail.get(mapped):
                    detail[mapped] = value[:500]


def _extract_attachments(soup, base_url, detail_path):
    """从详情页 HTML 中提取附件链接。

    查找包含附件标识的 <a> 标签（如 "下载"、"招标文件" 等关键词）。

    Args:
        soup: BeautifulSoup 对象
        base_url: 站点根 URL
        detail_path: 详情页路径

    Returns:
        list[dict]: 附件列表 [{'name': ..., 'url': ...}]
    """
    from urllib.parse import urljoin

    attachments = []
    # 常见附件链接模式
    attachment_keywords = ['下载', '招标文件', '标书', '附件', '答疑', '补充通知']

    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        text = a_tag.get_text(strip=True)

        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        # 判断是否为附件链接
        is_attachment = False
        # 文件扩展名匹配
        for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar'):
            if ext in href.lower():
                is_attachment = True
                break
        # 关键词匹配
        if not is_attachment:
            for kw in attachment_keywords:
                if kw in text:
                    is_attachment = True
                    break

        if is_attachment:
            # 构建完整 URL
            if href.startswith('/'):
                full_url = base_url.rstrip('/') + href
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin(base_url.rstrip('/') + detail_path, href)

            attachments.append({
                'name': (text or 'attachment')[:200],
                'url': full_url[:500],
            })

    return attachments
