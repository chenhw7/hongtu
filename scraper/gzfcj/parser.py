# -*- coding: utf-8 -*-
"""gzfcj API 响应解析（将接口返回的条目转为 Lead dict）。

字段映射：
- 施工许可证公示：
    gcmc       → project_name  （工程名称）
    jsdd       → buyer_address （建设地点）
    jsdw       → buyer_name    （建设单位）
    sgdw       → agency_name   （施工单位）
    sgxkzh     → bidding_number（施工许可证号）
    pzrq       → publish_date  （批准日期）
    sgxkzt     → 存入 raw_data（状态）

- 竣工验收备案：
    pegcmc     → project_name  （工程名称）
    pejsdd     → buyer_address （工程地点）
    jsdw       → buyer_name    （建设单位）
    sgdw       → agency_name   （施工单位）
    babh       → bidding_number（竣工验收备案编号）
    peblrq     → publish_date  （通过日期）
    yjsbh      → 存入 raw_data（联合验收意见书编号）
    spbm       → 存入 raw_data（审批部门）
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 详情页 URL（广州住建局无独立详情页，指向列表页即可）
_PERMIT_PAGE_URL = 'https://zfcj.gz.gov.cn/zfcj/gczlaq/constructionPermitInformation'
_ACCEPTANCE_PAGE_URL = 'https://zfcj.gz.gov.cn/zfcj/gczlaq/completionAcceptance'


def _parse_date(date_str):
    """解析 gzfcj 接口返回的日期字符串（格式如 '2026/7/17 0:00:00'）。

    Returns:
        datetime.date or None
    """
    if not date_str:
        return None
    try:
        # 尝试多种格式
        for fmt in ('%Y/%m/%d %H:%M:%S', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
    except Exception:
        logger.debug('[gzfcj] 日期解析失败: %s', date_str)
    return None


def parse_permit_item(item):
    """将施工许可证公示 API 返回的单条数据转为 Lead dict。

    Args:
        item: API 返回 data 数组中的一个元素

    Returns:
        dict: Lead 字段字典（仅含非空字段）
    """
    lead = {
        'project_name': (item.get('gcmc') or '').strip()[:500],
        'buyer_address': (item.get('jsdd') or '').strip()[:200],
        'buyer_name': (item.get('jsdw') or '').strip()[:200],
        'agency_name': (item.get('sgdw') or '').strip()[:200],
        'bidding_number': (item.get('sgxkzh') or '').strip()[:100],
        'announcement_type': '施工许可证',
        'region': '广州市',
        'source_url': _PERMIT_PAGE_URL,
    }

    # 解析批准日期
    pub_date = _parse_date(item.get('pzrq'))
    if pub_date:
        lead['publish_date'] = pub_date

    # 状态字段存入 raw_data
    status = (item.get('sgxkzt') or '').strip()
    if status:
        lead['sgxkzt'] = status

    # 监理单位存入 raw_data
    jldw = (item.get('jldw') or '').strip()
    if jldw:
        lead['jldw'] = jldw

    # 过滤空值
    return {k: v for k, v in lead.items() if v not in (None, '')}


def parse_acceptance_item(item):
    """将竣工验收备案 API 返回的单条数据转为 Lead dict。

    Args:
        item: API 返回 data 数组中的一个元素

    Returns:
        dict: Lead 字段字典（仅含非空字段）
    """
    lead = {
        'project_name': (item.get('pegcmc') or '').strip()[:500],
        'buyer_address': (item.get('pejsdd') or '').strip()[:200],
        'buyer_name': (item.get('jsdw') or '').strip()[:200],
        'agency_name': (item.get('sgdw') or '').strip()[:200],
        'bidding_number': (item.get('babh') or '').strip()[:100],
        'announcement_type': '竣工验收备案',
        'region': '广州市',
        'source_url': _ACCEPTANCE_PAGE_URL,
    }

    # 解析通过日期
    pub_date = _parse_date(item.get('peblrq'))
    if pub_date:
        lead['publish_date'] = pub_date

    # 联合验收意见书编号存入 raw_data
    yjsbh = (item.get('yjsbh') or '').strip()
    if yjsbh:
        lead['yjsbh'] = yjsbh

    # 审批部门存入 raw_data
    spbm = (item.get('spbm') or '').strip()
    if spbm:
        lead['spbm'] = spbm

    # 过滤空值
    return {k: v for k, v in lead.items() if v not in (None, '')}
