# -*- coding: utf-8 -*-
"""gdcic 专用工具函数。"""
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def clean_gdcic_text(text):
    """清理文本：去除首尾空白、换行、多余空格。"""
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text.strip())
    return text


def parse_gdcic_date(date_str):
    """解析日期字符串，返回 (date_obj, time_str)。

    支持格式：
    - 2026-07-18
    - 2026/07/18
    - 2026.07.18
    - 2026年7月18日
    - 2026-07-18 10:30:00

    Args:
        date_str: 日期字符串

    Returns:
        (date_obj, time_str): date 对象和时间字符串（可能为 None）
    """
    if not date_str:
        return None, None

    date_str = str(date_str).strip()

    # 先尝试带时间格式
    m = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?', date_str)
    if m:
        try:
            date_obj = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            hour = int(m.group(4))
            minute = int(m.group(5))
            second = int(m.group(6)) if m.group(6) else 0
            time_str = '%02d:%02d:%02d' % (hour, minute, second)
            return date_obj, time_str
        except ValueError:
            pass

    # 仅日期格式（多种分隔符）
    m = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', date_str)
    if m:
        try:
            date_obj = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            return date_obj, None
        except ValueError:
            pass

    # 中文日期
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
    if m:
        try:
            date_obj = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            return date_obj, None
        except ValueError:
            pass

    return None, None


def extract_gdcic_phone(text):
    """从文本中提取电话号码。

    Args:
        text: 文本内容

    Returns:
        str: 电话号码，未找到返回空字符串
    """
    if not text:
        return ''

    # 手机号（优先检测，避免被座机正则误匹配）
    mobile_match = re.search(r'1[3-9]\d{9}', text)
    if mobile_match:
        return mobile_match.group(0)

    # 座机：区号-号码
    phone_match = re.search(r'(\d{3,4})[-\s](\d{7,8})', text)
    if phone_match:
        return '%s-%s' % (phone_match.group(1), phone_match.group(2))

    return ''
