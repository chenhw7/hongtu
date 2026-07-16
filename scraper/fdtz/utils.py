# -*- coding: utf-8 -*-
"""fdtz 专用工具函数：日期解析、投资金额解析。"""
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_fdtz_date(date_val):
    """解析发改委平台返回的日期值，支持多种格式。

    可能的格式：
    - Unix 时间戳（毫秒或秒，int/str）：1704067200000 / 1704067200
    - ISO 日期字符串："2024-01-01" / "2024-01-01 12:00:00"
    - 中文日期："2024年01月01日"
    - 紧凑格式："20240101"

    Args:
        date_val: 日期值（str / int / None）

    Returns:
        (date_str, time_str): ("YYYY-MM-DD", "HH:MM:SS") 二元组，
        解析失败时均为空字符串
    """
    if date_val is None:
        return '', ''

    # 处理数字时间戳（毫秒或秒）
    if isinstance(date_val, (int, float)):
        ts = date_val
        if ts > 1e12:
            ts = ts / 1000
        try:
            dt = datetime.fromtimestamp(ts)
            return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
        except (OSError, ValueError):
            return '', ''

    s = str(date_val).strip()
    if not s:
        return '', ''

    # 纯数字：可能是时间戳（毫秒/秒）或 YYYYMMDD
    if s.isdigit():
        n = int(s)
        if n > 1e12:
            # 毫秒时间戳
            try:
                dt = datetime.fromtimestamp(n / 1000)
                return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
            except (OSError, ValueError):
                pass
        elif n > 1e9:
            # 秒时间戳
            try:
                dt = datetime.fromtimestamp(n)
                return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
            except (OSError, ValueError):
                pass
        elif len(s) == 8:
            # YYYYMMDD
            try:
                dt = datetime.strptime(s, '%Y%m%d')
                return dt.strftime('%Y-%m-%d'), ''
            except ValueError:
                pass
        return '', ''

    # ISO 格式："2024-01-01" 或 "2024-01-01 12:00:00"
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                '%Y/%m/%d %H:%M:%S', '%Y/%m/%d'):
        try:
            dt = datetime.strptime(s, fmt)
            time_str = dt.strftime('%H:%M:%S') if '%H' in fmt else ''
            return dt.strftime('%Y-%m-%d'), time_str
        except ValueError:
            continue

    # 中文日期："2024年01月01日"
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime('%Y-%m-%d'), ''
        except ValueError:
            pass

    logger.debug('[fdtz] 无法解析日期: %r', date_val)
    return '', ''


def parse_investment(value):
    """解析投资金额，单位从万元转换为元。

    发改委平台 totalInvest 字段单位为万元（如 "1500.00"），
    Lead.budget_amount 存储单位为元，需乘以 10000。

    Args:
        value: 投资金额（str / int / float / None），单位：万元

    Returns:
        float or None: 以元为单位的投资金额，解析失败返回 None
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value) * 10000 if value else None

    s = str(value).strip().replace(',', '')
    if not s:
        return None

    # 去除"万元"/"元"等单位后缀
    unit_multiplier = 10000  # 默认万元
    if '亿元' in s or '亿' in s:
        unit_multiplier = 100000000
        s = re.sub(r'[亿元]', '', s)
    elif '万元' in s or '万' in s:
        unit_multiplier = 10000
        s = re.sub(r'[万元]', '', s)
    elif '元' in s:
        unit_multiplier = 1
        s = s.replace('元', '')

    try:
        num = float(s.strip())
        return num * unit_multiplier
    except ValueError:
        logger.debug('[fdtz] 无法解析投资金额: %r', value)
        return None
