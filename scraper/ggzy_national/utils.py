# -*- coding: utf-8 -*-
"""ggzy_national 专用工具函数。

全国公共资源交易平台的日期格式为 YYYY-MM-DD（无时分），与 Epoint 的
YYYY-MM-DD HH:MM:SS 不同，故提供独立的日期解析；预算与电话解析直接复用
Epoint 通用实现（scraper.epoint.utils），避免重复造轮子。
"""
import logging
import re
from datetime import date, datetime

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})')
_PHONE_MOBILE = re.compile(r'1[3-9]\d{9}')
_PHONE_LANDLINE = re.compile(r'0\d{2,3}-?\d{7,8}')


def parse_publish_date(date_str):
    """解析全国平台发布日期。

    响应字段 publishTime 为 'YYYY-MM-DD'，详情页可能出现 'YYYY年MM月DD日' 等变体。

    Args:
        date_str: 原始日期字符串

    Returns:
        date or None: 解析成功返回 date 对象
    """
    if not date_str:
        return None
    date_str = str(date_str).strip()
    m = _DATE_RE.search(date_str)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_budget(text):
    """从文本中提取预算金额（元），支持 亿/万/元 单位。

    复用 Epoint 的解析规则。如 '731.49 万元' -> 7314900.0。
    """
    if not text:
        return None
    text = str(text).strip()

    # 带单位的金额：先匹配 'X.XX 亿元/万元/元'
    m = re.search(r'([\d,]+\.?\d*)\s*(亿元|万元|元)', text)
    if m:
        amount = float(m.group(1).replace(',', ''))
        unit = m.group(2)
        if unit == '亿元':
            return amount * 1e8
        if unit == '万元':
            return amount * 1e4
        return amount

    # 纯数字 + 未标单位：保留原始值（元）
    m = re.search(r'([\d,]+\.\d{2})', text)
    if m:
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None
    return None


def parse_phone(text):
    """从文本中提取手机号或座机号。"""
    if not text:
        return None
    text = str(text)
    m = _PHONE_MOBILE.search(text)
    if m:
        return m.group(0)
    m = _PHONE_LANDLINE.search(text)
    if m:
        return m.group(0)
    return None


def clean_text(text):
    """清洗 HTML 文本：去标签 + 折叠空白。"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', str(text))
    text = re.sub(r'\s+', ' ', text).strip()
    return text
