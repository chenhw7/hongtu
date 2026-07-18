# -*- coding: utf-8 -*-
"""EpointWebBuilder 平台通用工具函数（日期解析、金额提取、HTML 清洗）。

供 epoint 模块内的 parser.py / detail.py 复用，不依赖具体省份配置。
"""
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_epoint_date(date_str):
    """解析 EpointWebBuilder 平台的日期字符串。

    支持格式：
        "2026-07-17 23:54:47"  -> (date(2026,7,17), "23:54")
        "2026-07-17"           -> (date(2026,7,17), None)
        "2026/07/17 10:30:00"  -> (date(2026,7,17), "10:30")
        "2026年07月17日"       -> (date(2026,7,17), None)

    Returns:
        (date, time_str) 二元组；解析失败时均为 None
    """
    if not date_str:
        return None, None
    date_str = str(date_str).strip()
    if not date_str:
        return None, None

    # 标准化中文日期分隔符
    normalized = date_str.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')

    # 尝试多种格式
    formats = [
        ('%Y-%m-%d %H:%M:%S', True),
        ('%Y-%m-%d %H:%M', True),
        ('%Y-%m-%d', False),
    ]
    for fmt, has_time in formats:
        try:
            dt = datetime.strptime(normalized[:len(fmt.replace('%Y','0000').replace('%m','00').replace('%d','00').replace('%H','00').replace('%M','00').replace('%S','00'))], fmt)
        except (ValueError, IndexError):
            try:
                dt = datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        if has_time:
            return dt.date(), dt.strftime('%H:%M')
        return dt.date(), None

    # 兜底：正则提取日期部分
    m = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', date_str)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            # 尝试提取时间
            tm = re.search(r'(\d{1,2}):(\d{2})', date_str)
            if tm:
                return d, f'{int(tm.group(1)):02d}:{tm.group(2)}'
            return d, None
        except ValueError:
            pass

    return None, None


def parse_budget(text):
    """从文本中提取金额（支持"万元"/"亿元"/"元"单位），返回以"元"为单位的 float。

    匹配示例：
        "投资金额：387.5万元"     -> 3875000.0
        "预算金额 1234567.89 元"  -> 1234567.89
        "合同估算价约1.5亿元"     -> 150000000.0
    """
    if not text:
        return None
    text = str(text)
    patterns = [
        (r'([\d,，]+\.?\d*)\s*亿\s*元', 100000000),
        (r'([\d,，]+\.?\d*)\s*万\s*元', 10000),
        (r'([\d,，]+\.?\d*)\s*元', 1),
    ]
    for pattern, multiplier in patterns:
        m = re.search(pattern, text)
        if m:
            num_str = m.group(1).replace(',', '').replace('，', '')
            try:
                return float(num_str) * multiplier
            except ValueError:
                continue
    return None


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


def clean_html_text(html_text):
    """清洗 HTML 片段，提取纯文本。

    ES API 返回的 content 字段可能包含 HTML 标签（高亮、摘要等），
    需要去除标签并清理多余空白。

    Args:
        html_text: 可能包含 HTML 标签的文本

    Returns:
        str: 清洗后的纯文本
    """
    if not html_text:
        return ''
    html_text = str(html_text).strip()
    if not html_text:
        return ''
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        text = soup.get_text(' ', strip=True)
    except Exception:
        # 简单去标签兜底
        text = re.sub(r'<[^>]+>', ' ', html_text)
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text
