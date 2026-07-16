# -*- coding: utf-8 -*-
"""ccgp 详情页解析。"""
import logging
import os
import re

from scraper.utils import parse_date, extract_attachments

logger = logging.getLogger(__name__)

# 详情页固定分段的边界关键词（用于从某分段标题截取到下一分段之前的文本）
_SECTION_BOUNDARY_RE = re.compile(
    r'(采购人信息|采购代理机构信息|项目联系方式|相关附件|评审专家|代理服务收费|公告期限|其他补充事宜|主办单位)'
)


def extract_section(text, header_pattern):
    """截取从 header_pattern 匹配处到下一个已知分段标题（或文末）之间的文本。"""
    m = re.search(header_pattern, text)
    if not m:
        return ''
    rest = text[m.end():]
    next_m = _SECTION_BOUNDARY_RE.search(rest)
    end = next_m.start() if next_m else len(rest)
    return rest[:end]


def extract_field(section_text, label_pattern):
    """在分段文本中按 '标签：值' 的形式提取字段值（取到该行换行为止）。

    label_pattern 用非捕获组包裹，避免其内部的 "|" 分支破坏后面的取值分组。
    """
    m = re.search(r'(?:%s)\s*[：:]\s*(.+)' % label_pattern, section_text)
    if not m:
        return None
    value = m.group(1).split('\n')[0].strip()
    return value or None


def fetch_detail(scraper, url):
    """获取详情页并解析补充信息。

    Returns:
        dict: 补充字段（联系人、电话、预算、截止日期、附件、原始HTML等）
    """
    html_text, soup = scraper.fetch_html(url)
    if soup is None:
        return {}

    try:
        detail = parse_detail(soup)
        detail['attachments'] = extract_attachments(soup, url)
        if html_text:
            detail['_raw_html'] = html_text
        return detail
    except Exception as e:
        logger.debug('[ccgp] 详情页解析失败 %s: %s', url, e)
        return {}


def parse_detail(soup):
    """解析详情页，提取更完整的信息。

    ccgp 聚合了全国各省级采购网站的公告，页面模板差异较大。
    解析优先级：
    1. 精确结构化提取——标题下方固定格式的发布时间"YYYY年MM月DD日 HH:MM"，
       以及末尾"1.采购人信息/2.采购代理机构信息/3.项目联系方式"三个固定分段
       （多数公告都遵循该模板，字段边界清晰，准确率高）。
    2. 兼容旧版/非标准页面——找不到固定分段时，退回原有的全文正则兜底匹配。
    """
    detail = {}

    # 获取全文文本用于正则匹配
    full_text = soup.get_text(separator='\n', strip=True)

    # ---- 1) 精确提取发布时间：标题区域固定格式 "YYYY年MM月DD日 HH:MM" ----
    dt_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})', full_text[:600])
    if dt_match:
        y, mo, d, h, mi = dt_match.groups()
        parsed_date = parse_date(f'{y}-{mo}-{d}')
        if parsed_date:
            detail['publish_date'] = parsed_date
            detail['publish_time'] = f'{int(h):02d}:{mi}'

    # ---- 2) 分段结构化提取：采购人信息 / 采购代理机构信息 / 项目联系方式 ----
    buyer_section = extract_section(full_text, r'采购人信息')
    agency_section = extract_section(full_text, r'采购代理机构信息')
    contact_section = extract_section(full_text, r'项目联系方式')

    buyer_phone_fallback = None
    if buyer_section:
        name = extract_field(buyer_section, r'名\s*称')
        addr = extract_field(buyer_section, r'地\s*址')
        tel = extract_field(buyer_section, r'联系方式|电\s*话')
        if name:
            detail['buyer_name'] = name[:200]
        if addr:
            detail['buyer_address'] = addr[:300]
        if tel:
            buyer_phone_fallback = tel[:50]

    if agency_section:
        name = extract_field(agency_section, r'名\s*称')
        tel = extract_field(agency_section, r'联系方式|电\s*话')
        if name:
            detail['agency_name'] = name[:200]
        if tel:
            detail['agency_phone'] = tel[:50]

    if contact_section:
        person = extract_field(contact_section, r'项目联系人|联\s*系\s*人')
        tel = extract_field(contact_section, r'电\s*话|联系方式')
        if person:
            detail['contact_person'] = person[:50]
        if tel:
            detail['phone'] = tel[:50]

    # 联系电话兜底：优先用"项目联系方式"分段的电话，没有则退回采购人电话
    if not detail.get('phone') and buyer_phone_fallback:
        detail['phone'] = buyer_phone_fallback

    # ---- 3) 兼容旧版页面结构：以下正则仅在结构化提取未命中时兜底 ----
    # 提取联系人
    contact_patterns = [
        r'联系人[（(]采购人[)）][：:]\s*(.+?)(?:\n|$)',
        r'采购人联系人[：:]\s*(.+?)(?:\n|$)',
        r'联\s*系\s*人[：:]\s*(.+?)(?:\n|$|,|，|电)',
        r'项目联系人[：:]\s*(.+?)(?:\n|$)',
    ]
    if not detail.get('contact_person'):
        for pattern in contact_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['contact_person'] = match.group(1).strip()[:50]
                break

    # 提取电话
    phone_patterns = [
        r'联系电话[（(]采购人[)）][：:]\s*([\d\-（）\(\)\s]+)',
        r'采购人电话[：:]\s*([\d\-（）\(\)\s]+)',
        r'联\s*系\s*电\s*话[：:]\s*([\d\-（）\(\)\s]+)',
        r'电\s*话[：:]\s*([\d\-（）\(\)\s]+)',
    ]
    if not detail.get('phone'):
        for pattern in phone_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['phone'] = match.group(1).strip()[:50]
                break

    # 提取预算金额
    budget_patterns = [
        r'预算金额[：:]\s*([\d,.]+)\s*(万元|元)',
        r'项目预算[：:]\s*([\d,.]+)\s*(万元|元)',
        r'采购预算[：:]\s*([\d,.]+)\s*(万元|元)',
        r'预算总金额[：:]\s*([\d,.]+)\s*(万元|元)',
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, full_text)
        if match:
            amount_str = match.group(1).replace(',', '').strip()
            try:
                amount = float(amount_str)
                # 判断单位：万元则转换为元
                if match.group(2) == '万元':
                    amount = amount * 10000
                detail['budget_amount'] = amount
            except ValueError:
                pass
            break

    # 提取投标截止日期
    deadline_patterns = [
        r'(?:投标|响应|递交|提交)[^。\n]*?截止[^\n]*?(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
        r'截止时间[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
        r'开标时间[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, full_text)
        if match:
            detail['deadline'] = parse_date(match.group(1))
            break

    # 尝试从详情页补充招标编号
    if not detail.get('bidding_number'):
        bid_patterns = [
            r'(?:招标编号|项目编号|公告编号|采购编号)[：:]\s*([A-Za-z0-9\-_/]+)',
        ]
        for pattern in bid_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['bidding_number'] = match.group(1).strip()
                break

    # 尝试补充采购单位
    if not detail.get('buyer_name'):
        buyer_patterns = [
            r'采购单位[：:]\s*(.+?)(?:\n|$|地)',
            r'采购人[：:]\s*(.+?)(?:\n|$|地)',
        ]
        for pattern in buyer_patterns:
            match = re.search(pattern, full_text)
            if match:
                detail['buyer_name'] = match.group(1).strip()[:200]
                break

    return detail
