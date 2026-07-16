# -*- coding: utf-8 -*-
"""ggzyjy 专用工具函数（日期解析、金额提取、richText HTML 解析、电话提取）。"""
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_ggzyjy_date(date_str):
    """解析粤公平平台日期字符串（格式 "yyyyMMddHHmmss"，如 "20260716190934"）。

    Returns:
        (date, time_str) 二元组；解析失败时均为 None
    """
    if not date_str:
        return None, None
    date_str = str(date_str).strip()
    if len(date_str) < 8:
        return None, None
    try:
        if len(date_str) >= 14:
            dt = datetime.strptime(date_str[:14], '%Y%m%d%H%M%S')
            return dt.date(), dt.strftime('%H:%M')
        elif len(date_str) >= 12:
            dt = datetime.strptime(date_str[:12], '%Y%m%d%H%M')
            return dt.date(), dt.strftime('%H:%M')
        else:
            dt = datetime.strptime(date_str[:8], '%Y%m%d')
            return dt.date(), None
    except ValueError:
        return None, None


def parse_budget(text):
    """从文本中提取金额（支持"万元"/"元"单位），返回以"元"为单位的 float。

    匹配示例：
        "最高投标限价：387.5万元"  -> 3875000.0
        "预算金额 1234567.89 元"   -> 1234567.89
        "合同估算价约350万元"      -> 3500000.0
    """
    if not text:
        return None
    text = str(text)
    # 匹配数字+单位（万元/元）
    patterns = [
        r'([\d,，]+\.?\d*)\s*万\s*元',
        r'([\d,，]+\.?\d*)\s*亿\s*元',
        r'([\d,，]+\.?\d*)\s*元',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            num_str = m.group(1).replace(',', '').replace('，', '')
            try:
                amount = float(num_str)
                if '亿' in pattern:
                    amount *= 100000000
                elif '万' in pattern:
                    amount *= 10000
                return amount
            except ValueError:
                continue
    return None


def parse_richtext_fields(html_text):
    """从 richText HTML 字符串中提取键值对（表格行 / 标签:值 形式）。

    粤公平详情接口的 richText 字段为 HTML 片段，通常包含 <table> 结构化数据，
    也可能以 "标签：值" 的纯文本段落形式出现。

    Returns:
        dict: 提取到的键值对（标签已去除冒号/空白，值已 strip）
    """
    if not html_text:
        return {}
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
    except Exception:
        return {}

    fields = {}

    # 1) 表格行提取：<tr><td>标签</td><td>值</td></tr>
    for tr in soup.find_all('tr'):
        tds = tr.find_all(['td', 'th'])
        if len(tds) >= 2:
            label = tds[0].get_text(strip=True).rstrip('：:').strip()
            value = tds[1].get_text(strip=True)
            if label and value:
                fields[label] = value[:500]
        # 某些表格有4列：标签/值/标签/值
        if len(tds) >= 4:
            label2 = tds[2].get_text(strip=True).rstrip('：:').strip()
            value2 = tds[3].get_text(strip=True)
            if label2 and value2:
                fields[label2] = value2[:500]

    # 2) 纯文本 "标签：值" 行提取（兜底）
    full_text = soup.get_text('\n', strip=True)
    for line in full_text.split('\n'):
        m = re.match(r'^[  ]*([^：:]{2,20})[：:]\s*(.+)$', line.strip())
        if m:
            label = m.group(1).strip()
            value = m.group(2).strip()
            if label and value and label not in fields:
                fields[label] = value[:500]

    return fields


def parse_phone(text):
    """从文本中提取电话号码（支持座机、手机号）。

    Returns:
        str or None: 提取到的电话号码
    """
    if not text:
        return None
    text = str(text)
    # 手机号
    m = re.search(r'1[3-9]\d{9}', text)
    if m:
        return m.group(0)
    # 座机号（区号-号码）
    m = re.search(r'(?:0\d{2,3}[-\s]?\d{7,8})', text)
    if m:
        return m.group(0).strip()
    # 通用号码
    m = re.search(r'(\d{3,4}[-\s]\d{7,8})', text)
    if m:
        return m.group(1).strip()
    return None
