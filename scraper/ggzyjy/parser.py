# -*- coding: utf-8 -*-
"""ggzyjy 列表项解析（将搜索 API 返回的 pageData 条目转为 Lead dict）。"""
import logging

from scraper.ggzyjy.utils import parse_ggzyjy_date

logger = logging.getLogger(__name__)

# 详情页 URL 模板（粤公平前端 hash 路由格式）
_DETAIL_URL_TPL = ('https://ygp.gdzwfw.gov.cn/#/44/new/jygg/v3/{trading_type}'
                   '?noticeId={notice_id}&projectCode={project_code}'
                   '&bizCode={biz_code}&siteCode={site_code}'
                   '&publishDate={publish_date}&titleDetails={title_details}'
                   '&classify={classify}')

# noticeSecondType -> titleDetails 映射
_TITLE_DETAILS_MAP = {
    'A': '工程建设',
    'D': '政府采购',
    'R': '其他交易',
}


def parse_item(item):
    """将单条 API 返回数据（pageData 数组中的一个元素）转为 Lead dict。

    字段映射：
        project_name       <- noticeTitle
        bidding_number     <- projectCode
        announcement_type  <- noticeThirdTypeDesc
        buyer_name         <- projectOwner
        region             <- regionName
        publish_date/time  <- publishDate (yyyyMMddHHmmss)
        source_url         <- 构建详情页 URL

    Args:
        item: 搜索 API 返回的 pageData 条目 dict

    Returns:
        dict: Lead 字段字典（仅含非空字段）
    """
    notice_id = (item.get('noticeId') or '').strip()
    project_code = (item.get('projectCode') or '').strip()
    site_code = (item.get('siteCode') or '440000').strip()
    trading_type = item.get('noticeSecondType', 'A')
    trading_process = (item.get('tradingProcess') or '').strip()
    publish_date_raw = (item.get('publishDate') or '').strip()
    classify = (item.get('noticeThirdType') or '').strip()

    lead = {
        'project_name': (item.get('noticeTitle') or '').strip()[:500],
        'bidding_number': project_code[:100],
        'announcement_type': (item.get('noticeThirdTypeDesc') or '').strip()[:50],
        'buyer_name': (item.get('projectOwner') or '').strip()[:200],
        'region': (item.get('regionName') or '').strip()[:50],
    }

    # 解析发布日期
    publish_date, publish_time = parse_ggzyjy_date(item.get('publishDate'))
    if publish_date:
        lead['publish_date'] = publish_date
    if publish_time:
        lead['publish_time'] = publish_time

    # 构建详情页 URL
    if notice_id:
        # bizCode: 优先用 tradingProcess，为空时取 noticeId 前4位
        biz_code = trading_process if trading_process else (
            notice_id[:4] if len(notice_id) >= 4 else '')
        title_details = _TITLE_DETAILS_MAP.get(trading_type, '工程建设')
        lead['source_url'] = _DETAIL_URL_TPL.format(
            trading_type=trading_type,
            notice_id=notice_id,
            project_code=project_code,
            biz_code=biz_code,
            site_code=site_code,
            publish_date=publish_date_raw,
            title_details=title_details,
            classify=classify,
        )[:500]

    # 保存元数据供详情请求使用
    lead['_notice_id'] = notice_id
    lead['_project_code'] = project_code
    lead['_site_code'] = site_code
    lead['_trading_type'] = trading_type
    lead['_trading_process'] = trading_process

    # 过滤空值
    return {k: v for k, v in lead.items() if v not in (None, '')}
