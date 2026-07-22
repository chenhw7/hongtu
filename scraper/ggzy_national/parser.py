# -*- coding: utf-8 -*-
"""ggzy_national 列表项解析（将 getTradList 接口返回的 records 条目转为 Lead dict）。

接口响应结构（详见报告 §3.2 / 第三章实测）：
    {
      "id": "0053c9692a91f23d4dee93a0323dbd5908c0",
      "publishTime": "2026-07-21",
      "businessTypeText": "工程建设",
      "informationType": "0101",
      "informationTypeText": "招标/资审公告",
      "province": "530000",
      "provinceText": "云南省",
      "title": "昆明市...招标公告",
      "url": "/information/deal/html/a/530000/0101/20260721/0053...html"
    }

详情页为静态 HTML，列表 url 为 /a/ 元信息页，完整正文在把 /a/ 换成 /b/ 的同路径页。
"""
import logging

from scraper.ggzy_national.regions import CODE_TO_NAME
from scraper.ggzy_national.utils import parse_publish_date

logger = logging.getLogger(__name__)


def _detail_url_from_list(list_url):
    """将列表项的 /a/ 元信息页 URL 转为 /b/ 完整正文页 URL。

    列表 url 形如: /information/deal/html/a/530000/0101/20260721/{id}.html
    正文 url 形如: /information/deal/html/b/530000/0101/20260721/{id}.html
    """
    if not list_url:
        return ''
    list_url = list_url.strip()
    # 仅替换首个 /html/a/ 段为 /html/b/
    return list_url.replace('/html/a/', '/html/b/', 1)


def _region_from_code(province_code, province_text):
    """省份码 + 文本 -> 标准化 region（优先用 provinceText，兜底用码表）。"""
    region = (province_text or '').strip()
    if region:
        return region[:50]
    code = (province_code or '').strip()
    if code in CODE_TO_NAME:
        return CODE_TO_NAME[code]
    return (province_code or '')[:50]


def parse_record(record):
    """将 getTradList 返回的单条记录转为 Lead dict。

    字段映射：
        project_name       <- title
        bidding_number     <- id（32 位 hash，唯一，作主去重键）
        announcement_type  <- informationTypeText
        region             <- provinceText（兜底 province 码表）
        source_url         <- /b/ 正文页绝对 URL
        publish_date       <- publishTime (YYYY-MM-DD)
        content            <- businessTypeText + informationTypeText 摘要
        _detail_path       <- /b/ 正文页路径（供详情请求使用）

    Args:
        record: getTradList 响应 data.records 中的单条 dict

    Returns:
        dict: Lead 字段字典（仅含非空字段），无 title 时返回空 dict
    """
    title = (record.get('title') or '').strip()
    if not title:
        return {}

    record_id = (record.get('id') or '').strip()
    list_url = (record.get('url') or '').strip()
    detail_path = _detail_url_from_list(list_url)

    lead = {
        'project_name': title[:500],
        # id 为 32 位 hash，作为主去重键（bidding_number 列有唯一约束）
        'bidding_number': record_id[:100],
        'announcement_type': (record.get('informationTypeText') or '').strip()[:50],
        'region': _region_from_code(record.get('province'), record.get('provinceText')),
    }

    # 发布日期
    publish_date = parse_publish_date(record.get('publishTime'))
    if publish_date:
        lead['publish_date'] = publish_date

    # 来源 URL（/b/ 正文页，便于人工核对）
    if detail_path:
        lead['source_url'] = detail_path[:500]

    # 摘要内容（列表页仅业务类型+信息类型，正文由详情页补充）
    biz_type = (record.get('businessTypeText') or '').strip()
    info_type = (record.get('informationTypeText') or '').strip()
    summary_parts = [p for p in (biz_type, info_type) if p]
    if summary_parts:
        lead['content'] = ' / '.join(summary_parts)[:2000]

    # 元数据供详情请求使用（详情请求需要完整正文 URL）
    lead['_detail_path'] = detail_path
    lead['_business_type'] = biz_type
    lead['_information_type'] = (record.get('informationType') or '').strip()

    # 过滤空值
    return {k: v for k, v in lead.items() if v not in (None, '')}
