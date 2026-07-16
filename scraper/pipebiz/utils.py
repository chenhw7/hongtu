# -*- coding: utf-8 -*-
"""pipebiz 专用工具函数（中国管道商务网 chinapipe.net）。"""
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def clean_pipebiz_text(text):
    """清理管道商务网特有的 HTML 杂质和多余空白。

    处理：
    - 去除 HTML 标签残留（&nbsp;、<br>、<p> 等）
    - 合并连续空白为单个空格
    - 去除首尾空白

    Args:
        text: 原始文本

    Returns:
        str: 清理后的文本
    """
    if not text:
        return ''
    # 替换常见 HTML 实体
    text = text.replace('&nbsp;', ' ').replace('&ensp;', ' ').replace('&emsp;', ' ')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    # 去除残留 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 合并连续空白（含换行、制表符）
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_pipebiz_date(date_str):
    """解析管道商务网的日期字符串。

    支持格式：
    - '2026-07-16'
    - '2026/07/16'
    - '2026.07.16'
    - '2026年07月16日'
    - '2026-07-16 10:30:00'
    - '07-16'（当年）

    Args:
        date_str: 日期字符串

    Returns:
        tuple: (date_str, time_str) 格式为 ('YYYY-MM-DD', 'HH:MM:SS')
               解析失败返回 ('', '')
    """
    if not date_str:
        return ('', '')

    date_str = date_str.strip()

    # 尝试多种格式
    formats = [
        ('%Y-%m-%d %H:%M:%S', True),
        ('%Y-%m-%d %H:%M', True),
        ('%Y-%m-%d', False),
        ('%Y/%m/%d %H:%M:%S', True),
        ('%Y/%m/%d', False),
        ('%Y.%m.%d', False),
        ('%Y年%m月%d日', False),
        ('%Y年%m月%d日 %H:%M', True),
    ]

    for fmt, has_time in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            date_part = dt.strftime('%Y-%m-%d')
            time_part = dt.strftime('%H:%M:%S') if has_time else ''
            return (date_part, time_part)
        except ValueError:
            continue

    # 尝试仅月日格式 'MM-DD' 或 'MM/DD'
    m = re.match(r'^(\d{1,2})[-/.](\d{1,2})$', date_str)
    if m:
        year = datetime.now().year
        month, day = int(m.group(1)), int(m.group(2))
        try:
            dt = datetime(year, month, day)
            return (dt.strftime('%Y-%m-%d'), '')
        except ValueError:
            pass

    return ('', '')


def extract_pipebiz_phone(text):
    """从文本中提取电话号码。

    支持：
    - 固话: 010-12345678, (010)12345678, 010 12345678
    - 手机: 13812345678, 138-1234-5678
    - 400 电话: 400-123-4567

    Args:
        text: 包含电话号码的文本

    Returns:
        str: 提取到的第一个电话号码，未找到返回空字符串
    """
    if not text:
        return ''

    # 400 电话
    m = re.search(r'400[-\s]?\d{3,4}[-\s]?\d{3,4}', text)
    if m:
        return m.group(0).strip()

    # 固话（带区号）
    m = re.search(r'(?:0\d{2,3})[-\s]?\d{7,8}', text)
    if m:
        return m.group(0).strip()

    # 带括号的区号
    m = re.search(r'\(0\d{2,3}\)\s*\d{7,8}', text)
    if m:
        return m.group(0).strip()

    # 手机号
    m = re.search(r'1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}', text)
    if m:
        return m.group(0).strip()

    return ''
