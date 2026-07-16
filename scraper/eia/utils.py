# -*- coding: utf-8 -*-
"""环评公示采集公共工具函数（纯函数，无外部依赖）。

通用日期解析和附件提取已上提到 scraper/utils.py，此处重新导出方便各适配器引用。
"""
import json
import logging
import re
from datetime import datetime

from scraper.utils import parse_date, extract_attachments  # noqa: F401

logger = logging.getLogger(__name__)

ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|doc|docx|xls|xlsx|zip|rar|7z|txt)(\?|$)', re.IGNORECASE)


def extract_government_phone(text):
    """从文本中提取生态环境主管部门的公众咨询电话。"""
    match = re.search(
        r'(?:联系电话|联系方式|电话)\s*[：:]\s*([0-9\-，,、\s]{5,40})',
        text or '',
    )
    if not match:
        return ''
    return re.split(r'传\s*真', match.group(1))[0].strip().rstrip('，,')


def classify_category(title):
    """按标题关键词分类公告类型（受理/审批前/批复）。"""
    if '受理' in title:
        return '受理公告'
    if '批复' in title:
        return '批复公告'
    if '批准决定' in title or '公示' in title:
        return '审批前公示'
    return '环评公示'


def extract_kv_tables(soup):
    """从详情页所有 <table> 提取结构化 key:value 字段。

    兼容两种表格形态：
    - 每行恰好2列：cells[0]为key，cells[1]为value。
    - 恰好2行且列数一致(>2列)：第1行为表头，第2行为数据，按列对齐 zip 成
      多组 key:value（如\"受理日期|项目名称|建设单位|...\"这种横向表格）。
    """
    data = {}
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) == 2:
            header_cells = [c.get_text(strip=True) for c in rows[0].find_all(['td', 'th'])]
            data_cells = [c.get_text(strip=True) for c in rows[1].find_all(['td', 'th'])]
            if len(header_cells) == len(data_cells) and len(header_cells) > 2:
                for k, v in zip(header_cells, data_cells):
                    if k:
                        data[k] = v
                continue
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key:
                    data[key] = value
    return data


def parse_source_files(value, context):
    """将附件元数据（JSON 字符串/list/dict）统一转为 list[dict]。"""
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        logger.warning('[eia] 附件元数据 JSON 解析失败（%s），保留原文', context)
        return value
    if isinstance(decoded, dict):
        return [decoded]
    return decoded


# extract_attachments 已上提到 scraper/utils.py，此处通过模块顶部 import 重新导出。
# 如需 eia 特有的附件提取逻辑（例如不同的扩展名匹配），在此处添加包装函数。