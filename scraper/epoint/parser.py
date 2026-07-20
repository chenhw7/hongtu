# -*- coding: utf-8 -*-
"""EpointWebBuilder ES API JSON 响应 → Lead dict 通用解析。

将 getFullTextDataNew 接口返回的每条 record 转为项目统一的 Lead dict。
"""
import logging

from scraper.epoint.utils import parse_epoint_date, clean_html_text

logger = logging.getLogger(__name__)


def parse_record(record, scraper):
    """将 ES API 返回的单条 record 转为 Lead dict。

    字段映射：
        project_name       <- record['title']
        publish_date/time  <- record['webdate']（YYYY-MM-DD HH:MM:SS）
        region             <- record['infod']（地区名）
        buyer_address      <- record['infod']
        source_url         <- base_url + record['linkurl']
        announcement_type  <- record['categoryname']
        content（摘要）    <- record['content']

    Args:
        record: ES API 返回的 records 数组中的单个元素 dict
        scraper: EpointBaseScraper 实例（提供 base_url / REGIONS）

    Returns:
        dict: Lead 字段字典（仅含非空字段）；无 project_name 时返回 None
    """
    title = (record.get('title') or '').strip()[:500]
    if not title:
        return None

    lead = {
        'project_name': title,
        'announcement_type': (record.get('categoryname') or '').strip()[:50],
        'region': (record.get('infod') or '').strip()[:50],
        'buyer_address': (record.get('infod') or '').strip()[:200],
    }

    # 解析发布日期（浙江用 webdate，江苏/四川用 infodatepx）
    date_field = 'webdate'
    if scraper is not None:
        tf = getattr(scraper, 'TIME_FIELD', None)
        if isinstance(tf, str) and tf:
            date_field = tf
    publish_date, publish_time = parse_epoint_date(record.get(date_field))
    if publish_date:
        lead['publish_date'] = publish_date
    if publish_time:
        lead['publish_time'] = publish_time

    # 构建详情页 URL
    linkurl = (record.get('linkurl') or '').strip()
    if linkurl:
        lead['source_url'] = (scraper.base_url.rstrip('/') + linkurl)[:500]
        # 保留相对路径供详情页请求使用
        lead['_detail_path'] = linkurl

    # 摘要内容
    content = clean_html_text(record.get('content') or '')
    if content:
        lead['content'] = content[:2000]

    # 通过 infoc（地区码）关联 REGIONS，补充地区信息
    infoc = (record.get('infoc') or '').strip()
    if infoc and scraper.REGIONS:
        # 尝试精确匹配和前缀匹配（6位码 -> 4位码前缀）
        region_info = scraper.REGIONS.get(infoc)
        if region_info:
            lead['region'] = region_info.get('name', lead.get('region', ''))[:50]

    # 过滤空值
    return {k: v for k, v in lead.items() if v not in (None, '')}
