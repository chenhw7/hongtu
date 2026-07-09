# -*- coding: utf-8 -*-
"""广东省政府采购信息爬虫

gdgpo.czt.gd.gov.cn 前端已迁移为 Vue SPA（原直接 HTML 解析方案已失效），但
2026-07-09 抓包确认其后端 gpcms 提供了两个完全公开、无需登录/无签名鉴权的
JSON REST 接口，可直接用 httpx 调用，无需浏览器：

- 列表：GET /gpcms/rest/web/v2/info/selectInfoForIndex
  按频道(channel) + 发布时间区间 + 分页参数返回"采购项目信息"频道列表
  （采购意向公开/采购计划/采购需求/资格预审公告/采购公告/中标结果/更正/
  终止/合同/验收公告等，即最有采集价值的招投标信息）。
- 详情：GET /gpcms/rest/web/v2/info/getInfoById?id=<row.id>
  返回该条目的完整信息，包括未截断的正文 HTML（content 字段），附件下载
  链接直接内嵌在正文 HTML 里（<a href="https://.../gpx-bid-file/....pdf?
  accessCode=...">），无需再单独请求详情页面。

这两个接口都不需要签名/验证码，比 ccgp 聚合页的正则解析更可靠（预算、
联系人、代理机构等均为结构化字段），因此本采集器直接对接该 API，不再
依赖 CcgpScraper。

注：同域下的"广东省框架协议电子化采购系统"(gpfa-main-web) 用的是完全独立
的另一套后端，其列表接口带自定义签名反爬(sign/nsssjss/timestamp 请求头)，
本采集器不处理该部分。
"""
import logging
import re
from datetime import datetime, timedelta

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# gdgpo maincms 站点固定标识（GET .../index/getDeploymentSiteId 查得，长期稳定）
_SITE_ID = 'cd64e06a-21a7-4620-aebc-0576bab7e07a'

# "采购项目信息"频道（对应站点导航"采购项目信息"栏目，含全部招投标类公告）
_CHANNEL_CGGG = 'fca71be5-fc0c-45db-96af-f513e9abda9d,95ff31f3-a1af-4bc4-b1a2-54c894476193'

_API_BASE = 'https://gdgpo.czt.gd.gov.cn/gpcms/rest/web/v2/info'
_LIST_URL = _API_BASE + '/selectInfoForIndex'
_DETAIL_URL = _API_BASE + '/getInfoById'

_PAGE_SIZE = 20

# 伪关键词：不做标题过滤，全量采集"采购项目信息"频道（频道本身已是高价值信息，
# 无需像 ccgp 那样区分中央/地方公告频道）
_CHANNEL_KEYWORD = 'channel:cggg'

# noticeType 编码前缀 -> 公告类型中文名（GET .../index/getDictInfo?dictType=
# lmy-xmcg-noticeType 查得；实际数据里的编码常带一位子类型后缀，如"001011"，
# 按前缀匹配即可，不要求完全相等）
_NOTICE_TYPE_PREFIXES = [
    ('59', '采购意向公开'),
    ('001051', '单一来源公示'),
    ('001101', '采购计划'),
    ('001059', '采购需求'),
    ('001052', '资格预审公告'),
    ('001053', '资格预审公告'),
    ('00101', '采购公告'),
    ('00102', '中标（成交）结果公告'),
    ('00103', '更正公告'),
    ('00105B', '更正公告'),
    ('001004', '终止公告'),
    ('001006', '终止公告'),
    ('001054', '合同公告'),
    ('001009', '验收公告'),
    ('00105A', '验收公告'),
]
# 按前缀长度从长到短排序，保证更具体的前缀优先匹配
_NOTICE_TYPE_PREFIXES.sort(key=lambda pair: len(pair[0]), reverse=True)

# 详情正文 HTML 中的附件下载链接识别（沿用 ccgp 的扩展名约定）
_ATTACHMENT_HREF_RE = re.compile(
    r'href="(https?://[^"]+\.(?:pdf|docx?|xlsx?|zip|rar|7z|txt)(?:\?[^"]*)?)"',
    re.IGNORECASE,
)


class GdgpoScraper(BaseScraper):
    """广东省政府采购网爬虫（直接对接 gpcms 公开 REST 接口，非浏览器方案）"""

    source_type = 'gdgpo'
    base_url = _LIST_URL
    referer = 'https://gdgpo.czt.gd.gov.cn/maincms-web/noticeInformationGd'

    # ------------------------------------------------------------------
    # 主流程钩子：run() 按 keyword × page 循环调用本方法
    # ------------------------------------------------------------------
    def _scrape_page(self, keyword, page):
        """采集"采购项目信息"频道第 page 页

        Args:
            keyword: 空字符串或 'channel:cggg' 表示不按标题过滤、全量采集；
                     其他非空字符串则作为标题关键词过滤（title 参数）。
            page: 页码，从 1 开始

        Returns:
            list[dict] 线索列表；None 表示请求失败；[] 表示该页无更多结果
        """
        title_filter = ''
        if keyword and keyword != _CHANNEL_KEYWORD:
            title_filter = keyword

        end_time = datetime.now()
        start_time = end_time - timedelta(days=365)
        params = {
            'title': title_filter,
            'region': '',
            'siteId': _SITE_ID,
            'channel': _CHANNEL_CGGG,
            'currPage': page,
            'pageSize': _PAGE_SIZE,
            'noticeType': '',
            'regionCode': '',
            'cityOrArea': '',
            'purchaseManner': '',
            'openTenderCode': '',
            'purchaser': '',
            'agency': '',
            'purchaseNature': '',
            'operationStartTime': start_time.strftime('%Y-%m-%d 00:00:00'),
            'operationEndTime': end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'verifyCode': '',
            'subChannel': 'false',
        }

        response = self.fetch(_LIST_URL, params=params, extra_headers={'Accept': 'application/json'})
        if response is None:
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning('[gdgpo] 列表接口返回非JSON: %s', response.text[:200])
            return None

        if payload.get('code') != '200':
            logger.warning('[gdgpo] 列表接口返回异常: %s', payload.get('msg'))
            return None

        rows = ((payload.get('data') or {}).get('rows')) or []
        if not rows:
            return []

        leads = []
        for row in rows:
            self._check_pause_and_stop()
            lead = self._row_to_lead(row)
            detail = self._fetch_detail(row.get('id'))
            if detail:
                lead.update(detail)
            leads.append(lead)

        logger.info('[gdgpo] 第 %d 页解析到 %d 条结果', page, len(leads))
        return leads

    # ------------------------------------------------------------------
    # 详情：全文正文 + 附件
    # ------------------------------------------------------------------
    def _fetch_detail(self, row_id):
        """调用 getInfoById 获取完整详情（全文正文、附件下载链接）

        Returns:
            dict: 补充/覆盖字段，请求失败时返回 {}
        """
        if not row_id:
            return {}

        response = self.fetch(_DETAIL_URL, params={'id': row_id}, extra_headers={'Accept': 'application/json'})
        if response is None:
            return {}

        try:
            payload = response.json()
        except ValueError:
            return {}

        if payload.get('code') != '200':
            return {}

        data = payload.get('data') or {}
        detail = self._row_to_lead(data)

        content_html = data.get('content') or ''
        if content_html:
            detail['attachments'] = self._extract_attachments(content_html)
            detail['_raw_html'] = content_html

        return detail

    @staticmethod
    def _extract_attachments(content_html):
        """从详情正文 HTML 中提取附件下载链接（附件链接直接内嵌在正文里）"""
        attachments = []
        seen = set()
        for url in _ATTACHMENT_HREF_RE.findall(content_html):
            if url in seen:
                continue
            seen.add(url)
            name = url.rsplit('/', 1)[-1].split('?', 1)[0] or 'attachment'
            attachments.append({'name': name[:200], 'url': url})
        return attachments

    # ------------------------------------------------------------------
    # 字段映射：API 返回的 row/detail dict -> Lead 字段
    # ------------------------------------------------------------------
    def _row_to_lead(self, row):
        """把列表行或详情数据映射为 Lead 字段字典（两者字段名一致，可复用）"""
        lead = {
            'project_name': (row.get('title') or '').strip()[:500],
            'bidding_number': (row.get('openTenderCode') or '').strip()[:100],
            'announcement_type': self._notice_type_name(row),
            'buyer_name': (row.get('purchaser') or row.get('author') or '').strip()[:200],
            'buyer_address': (row.get('purchaserAddr') or '').strip()[:300],
            'region': (row.get('regionName') or '').strip()[:50],
            'contact_person': (row.get('purchaserLinkMan') or row.get('contactPerson') or '').strip()[:50],
            'phone': (row.get('purchaserLinkPhone') or row.get('contactNumber') or '').strip()[:50],
            'agency_name': (row.get('agency') or '').strip()[:200],
            'agency_phone': (row.get('agentLinkPhone') or '').strip()[:50],
            'source_url': '%s?id=%s' % (_DETAIL_URL, row.get('id', '')),
        }

        budget = self._parse_amount(row.get('budget'))
        if budget is not None:
            lead['budget_amount'] = budget

        publish_date, publish_time = self._parse_datetime(
            row.get('publishTime') or row.get('noticeTime') or row.get('addtime')
        )
        if publish_date:
            lead['publish_date'] = publish_date
        if publish_time:
            lead['publish_time'] = publish_time

        deadline, _ = self._parse_datetime(row.get('openTenderTime') or row.get('noticeEndTime'))
        if deadline:
            lead['deadline'] = deadline

        # 过滤掉空字符串，避免覆盖详情阶段已填充的更完整字段
        return {k: v for k, v in lead.items() if v not in (None, '')}

    @staticmethod
    def _notice_type_name(row):
        """按 noticeType 编码前缀匹配公告类型中文名，匹配不到则原样返回编码"""
        name = (row.get('noticeTypeName') or '').strip()
        if name:
            return name[:50]
        code = (row.get('noticeType') or '').strip()
        if not code:
            return ''
        for prefix, cn_name in _NOTICE_TYPE_PREFIXES:
            if code.startswith(prefix):
                return cn_name
        return code[:50]

    @staticmethod
    def _parse_amount(value):
        """解析预算金额字符串（如 "3870000.0000"）为 float"""
        if value in (None, ''):
            return None
        try:
            return float(str(value).replace(',', ''))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_datetime(value):
        """解析 "YYYY-MM-DD HH:MM:SS" 字符串，返回 (date, 'HH:MM') 二元组"""
        if not value:
            return None, None
        value = str(value).strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(value, fmt)
                time_str = dt.strftime('%H:%M') if fmt != '%Y-%m-%d' else None
                return dt.date(), time_str
            except ValueError:
                continue
        return None, None

