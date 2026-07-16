# -*- coding: utf-8 -*-
"""ccgp 专用工具函数。

通用逻辑已上提到 scraper/utils.py，此处仅保留 ccgp 特有的格式处理。
"""
from scraper.utils import parse_date as _parse_date


def parse_ccgp_date(date_str):
    """ccgp 日期解析（调用通用 parse_date，补充 ccgp 特有格式）。"""
    return _parse_date(date_str)
