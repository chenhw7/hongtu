# -*- coding: utf-8 -*-
"""ggzy_national 详情页（/b/ 正文 HTML）解析。

全国平台详情页为静态 HTML，分两层（详见报告 §3.3）：
  /a/ 元信息页（标题、项目编号、附件清单，无正文）
  /b/ 完整公告正文（字段极完整）

/b/ 正文实测字段（昆明燃气管道改造项目）：
  招标项目名称、资金来源、建设规模、行业分类、工程类型、招标方式、
  建设单位、经办人、办公电话、招标代理机构、项目负责人、
  标段编号、标段合同估算价、计划工期、资质要求、开标时间/地点、
  招标文件获取截止时间。

本模块使用 BeautifulSoup 提取表格 + 段落 "标签：值" 形式的字段。
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.ggzy_national.utils import parse_budget, parse_phone, parse_publish_date

logger = logging.getLogger(__name__)

_BASE_URL = 'https://www.ggzy.gov.cn'

# /b/ 正文页中的中文标签 -> Lead 字段映射
_LABEL_MAP = {
    '项目名称': 'project_name',
    '工程名称': 'project_name',
    '招标项目名称': 'project_name',
    '项目编号': 'bidding_number',
    '招标项目编号': 'bidding_number',
    '项目代码': 'bidding_number',
    '标段编号': '_bid_section',
    # 业主/招标人
    '建设单位': 'buyer_name',
    '招标人': 'buyer_name',
    '采购人': 'buyer_name',
    '项目业主': 'buyer_name',
    '项目法人': 'buyer_name',
    '经办人': 'contact_person',
    '联系人': 'contact_person',
    '招标人联系人': 'contact_person',
    '建设单位联系人': 'contact_person',
    '办公电话': 'phone',
    '联系电话': 'phone',
    '招标人联系电话': 'phone',
    '联系方式': 'phone',
    # 地址
    '建设地点': 'buyer_address',
    '工程地点': 'buyer_address',
    '项目地点': 'buyer_address',
    '地址': 'buyer_address',
    # 招标代理
    '招标代理机构': 'agency_name',
    '代理机构': 'agency_name',
    '代理机构联系电话': 'agency_phone',
    '招标代理联系电话': 'agency_phone',
    # 预算
    '标段合同估算价': '_budget_text',
    '合同估算价': '_budget_text',
    '预算金额': '_budget_text',
    '项目预算': '_budget_text',
    '最高投标限价': '_budget_text',
    '投资金额': '_budget_text',
    # 截止/开标
    '开标时间': '_deadline_text',
    '投标截止时间': '_deadline_text',
    '投标文件递交截止时间': '_deadline_text',
    # 其他存入 raw_data
    '资金来源': '_fund_source',
    '建设规模': '_build_scale',
    '资质要求': '_qualification',
    '计划工期': '_build_period',
}


def fetch_detail(scraper, api, detail_path):
    """获取并解析 /b/ 详情页，返回补充字段。

    Args:
        scraper: GgzyNationalScraper 实例（用于 pause/stop 检查）
        api: GgzyNationalApi 实例（提供 fetch_detail_html）
        detail_path: /b/ 正文页路径

    Returns:
        dict: 补充字段（联系人、电话、预算、截止日期、附件、原始 HTML 等），
              请求失败返回空 dict
    """
    if not detail_path:
        return {}

    html_text = api.fetch_detail_html(detail_path)
    if not html_text:
        return {}

    try:
        soup = BeautifulSoup(html_text, 'lxml')
    except Exception:
        soup = BeautifulSoup(html_text, 'html.parser')

    detail = {}

    # 1) 表格键值对
    _parse_tables(soup, detail)
    # 2) 段落 "标签：值" 兜底
    _parse_text_labels(soup, detail)
    # 3) 附件
    attachments = _extract_attachments(soup, detail_path)
    if attachments:
        detail['attachments'] = attachments
    # 4) 原始 HTML 快照
    detail['_raw_html'] = html_text

    # 过滤空值
    return {k: v for k, v in detail.items() if v not in (None, '')}


def _parse_tables(soup, detail):
    """从 HTML 表格提取键值对（支持 2 列与 4 列布局）。"""
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) >= 2:
                _extract_cell_pair(cells[0], cells[1], detail)
            if len(cells) >= 4:
                _extract_cell_pair(cells[2], cells[3], detail)


def _extract_cell_pair(label_cell, value_cell, detail):
    """从一对表格单元格提取字段。"""
    label = label_cell.get_text(strip=True).rstrip('：:').strip()
    value = value_cell.get_text(strip=True)
    if not label or not value:
        return

    mapped = _LABEL_MAP.get(label)
    if not mapped:
        return

    if mapped.startswith('_'):
        if mapped == '_budget_text':
            budget = parse_budget(value)
            if budget is not None and not detail.get('budget_amount'):
                detail['budget_amount'] = budget
        elif mapped == '_deadline_text':
            deadline_date = parse_publish_date(value)
            if deadline_date and not detail.get('deadline'):
                detail['deadline'] = deadline_date
        elif not detail.get(mapped):
            detail[mapped] = value[:500]
    else:
        if not detail.get(mapped):
            detail[mapped] = value[:500]

    # 电话兜底：标签为办公电话/联系电话时即使未命中 LABEL 也提取
    if not detail.get('phone') and label in ('办公电话', '联系电话', '联系方式'):
        phone = parse_phone(value)
        if phone:
            detail['phone'] = phone[:50]


def _parse_text_labels(soup, detail):
    """从正文段落提取 '标签：值' 形式（兜底方案）。"""
    text = soup.get_text('\n', strip=True)
    for line in text.split('\n'):
        m = re.match(r'^[  ]*([^：:]{2,20})[：:]\s*(.+)$', line.strip())
        if not m:
            continue
        label = m.group(1).strip()
        value = m.group(2).strip()
        if not label or not value:
            continue
        mapped = _LABEL_MAP.get(label)
        if not mapped:
            continue
        if mapped.startswith('_'):
            if mapped == '_budget_text' and not detail.get('budget_amount'):
                budget = parse_budget(value)
                if budget is not None:
                    detail['budget_amount'] = budget
            elif mapped == '_deadline_text' and not detail.get('deadline'):
                deadline_date = parse_publish_date(value)
                if deadline_date:
                    detail['deadline'] = deadline_date
            elif not detail.get(mapped):
                detail[mapped] = value[:500]
        elif not detail.get(mapped):
            detail[mapped] = value[:500]


def _extract_attachments(soup, detail_path):
    """提取附件链接（招标文件 .BZBJ、PDF、答疑等）。"""
    attachments = []
    attachment_keywords = ['下载', '招标文件', '标书', '附件', '答疑', '补充通知']

    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        text = a_tag.get_text(strip=True)
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        is_attachment = False
        for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar',
                    '.bzbj', '.zbs'):
            if ext in href.lower():
                is_attachment = True
                break
        if not is_attachment:
            for kw in attachment_keywords:
                if kw in text:
                    is_attachment = True
                    break
        if not is_attachment:
            continue

        if href.startswith('/'):
            full_url = _BASE_URL.rstrip('/') + href
        elif href.startswith('http'):
            full_url = href
        else:
            full_url = urljoin(_BASE_URL.rstrip('/') + detail_path, href)

        attachments.append({
            'name': (text or 'attachment')[:200],
            'url': full_url[:500],
        })
    return attachments
