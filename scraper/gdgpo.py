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

另外，同域下的"广东省框架协议电子化采购系统"(gpfa-main-web) 虽然浏览器里
每次请求都会带上 sign/nsssjss/timestamp 这类请求头，但经实测这些签名后端
并未真正校验——同样的接口不带任何签名头直接用 httpx 调用也能拿到 200 和
正常数据（2026-07-09 用 httpx 反复验证过，见下方 gpfa 部分实现）。此前误以
为这是强制签名反爬、需要 Playwright 才能绕过，是没有实测直接下的错误结论。
目前已接入两个 gpfa 频道：
1. "框架协议征集公告"家族（征集/更正/暂停/恢复公告，接口
   pagingKcAgreementNotice），返回结果里的 path 字段直接就是可公开访问的静态
   详情页 HTML（同样无需签名）。
2. "框架协议二次竞价采购公告"（即 noticeDetail?noticeGuid=... 这类，正文内容
   比"征集公告"更接近具体招标文件，信息量也更大），列表接口是
   GET /gateway/gpfa-bpoc/notice/v1/ignore/getNoticeList?noticeType=0&
   projectType=17&regionGuid=...&pageSize=...&pageNum=...&webApp=2&
   upgradeRegionFlag=true（2026-07-09 从 gpfa-main-web 首页公告预览组件的
   Vue 实例里直接调用 tapNotice(3) 方法反查到的，同样完全公开无需签名），
   详情接口就是前面提到的 getNoticeDetailExceptGD?noticeGuid=<row.noticeGuid>。
"""
import logging
import re
import time
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

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

# ------------------------------------------------------------------
# gpfa "框架协议电子化采购系统" —— 框架协议征集公告家族
# ------------------------------------------------------------------
_GPFA_LIST_URL = 'https://gdgpo.czt.gd.gov.cn/gateway/gpfa-bpoc/api/notice/kc/v1/ignore/pagingKcAgreementNotice'

# 伪关键词：采集 gpfa 框架协议征集公告家族（征集/更正/暂停/恢复公告）
_CHANNEL_KEYWORD_GPFA = 'channel:gpfa'

_GPFA_NOTICE_TYPES = ['gpfa_notice', 'gpfa_notice_modify', 'gpfa_notice_resume', 'gpfa_notice_pause']
_GPFA_TYPE_NAME = {
    'gpfa_notice': '框架协议征集公告',
    'gpfa_notice_modify': '框架协议征集更正公告',
    'gpfa_notice_resume': '框架协议征集恢复公告',
    'gpfa_notice_pause': '框架协议征集暂停公告',
}

# 详情静态页固定分段"二、征集人信息"里的字段：1、征集人：xxx 2、联系人：xxx
# 3、联系方式：xxx 4、联系地址：xxx（截取到下一个"三、"编号分段之前）
_GPFA_SECTION_RE = re.compile(r'二、征集人信息(.+?)三、', re.DOTALL)

# ------------------------------------------------------------------
# gpfa "框架协议电子化采购系统" —— 框架协议二次竞价采购公告（noticeGuid）
# ------------------------------------------------------------------
_GPFA_XJJ_LIST_URL = 'https://gdgpo.czt.gd.gov.cn/gateway/gpfa-bpoc/notice/v1/ignore/getNoticeList'
_GPFA_XJJ_DETAIL_URL = 'https://gdgpo.czt.gd.gov.cn/gateway/gpfa-bpoc/api/notice/other/v1/ignore/getNoticeDetailExceptGD'
# 真实前端详情页（浏览器里点击“采购公告”分类进入的落地页，用户已验证可直接打开）
_GPFA_XJJ_PAGE_URL = 'https://gdgpo.czt.gd.gov.cn/gpfa-main-web/basic/noticeDetail'

# 伪关键词：采集 gpfa 框架协议二次竞价采购公告（noticeType=0, projectType=17）
_CHANNEL_KEYWORD_GPFA_XJJ = 'channel:gpfaxjj'
_GPFA_XJJ_ANNOUNCEMENT_TYPE = '框架协议二次竞价采购公告'

# 伪关键词：采集 gpfa 框架协议二次竞价成交结果公告（noticeType=1）——
# 与上面的二次竞价采购公告同源（同一个 getNoticeList/getNoticeDetailExceptGD接口，
# 只是 noticeType 不同），告知谁中标了、中标价多少，对市场价格/竞争对手有参考
# 价值，且采购人信息仍可用于后续回访（同一采购人往往会有下一轮采购需求）。
_CHANNEL_KEYWORD_GPFA_RESULT = 'channel:gpfaresult'
_GPFA_RESULT_ANNOUNCEMENT_TYPE = '框架协议二次竞价成交结果公告'

# 成交结果详情正文固定结构："二、成交供应商"表格标题行后跟着数据行：
# 成交供应商/地址/成交金额（元）三个列名后面紧接对应的三个值
_GPFA_RESULT_WINNER_RE = re.compile(
    r'二、成交供应商\s*\n\s*成交供应商\s*\n\s*地址\s*\n\s*成交金额（元）\s*\n\s*([^\n]+)\n\s*([^\n]+)\n\s*([\d,.]+)'
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
        """采集单页数据

        Args:
            keyword: 空字符串或 'channel:cggg' 表示不按标题过滤、全量采集 maincms
                     "采购项目信息"频道；'channel:gpfa' 表示改为采集 gpfa 框架协议
                     征集公告家族；'channel:gpfaxjj' 表示改为采集 gpfa 框架协议
                     二次竞价采购公告；'channel:gpfaresult' 表示改为采集 gpfa 框架
                     协议二次竞价成交结果公告；其他非空字符串则作为 maincms 的标题
                     关键词过滤。
            page: 页码，从 1 开始

        Returns:
            list[dict] 线索列表；None 表示请求失败；[] 表示该页无更多结果
        """
        if keyword == _CHANNEL_KEYWORD_GPFA:
            return self._scrape_gpfa_page(page)
        if keyword == _CHANNEL_KEYWORD_GPFA_XJJ:
            return self._scrape_gpfa_xjj_page(page)
        if keyword == _CHANNEL_KEYWORD_GPFA_RESULT:
            return self._scrape_gpfa_xjj_page(page, notice_type=1, announcement_type=_GPFA_RESULT_ANNOUNCEMENT_TYPE)

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
    # gpfa 框架协议征集公告家族（征集/更正/暂停/恢复公告）
    # ------------------------------------------------------------------
    def _scrape_gpfa_page(self, page):
        """采集 gpfa "框架协议信息/项目公告"里的征集公告家族第 page 页

        列表接口 pagingKcAgreementNotice 返回的每条记录自带 path 字段，是可以
        直接公开访问的静态详情页 HTML（无需再调用签名 API），详情抓取直接
        GET 该 path 即可。

        Returns:
            list[dict] 线索列表；None 表示请求失败；[] 表示该页无更多结果
        """
        body = {
            'agreementTypeCode': 0,
            'regionCode': '440000',
            'regionGuid': '2137',
            'pageSize': _PAGE_SIZE,
            'pageNum': page,
            'noticeTypeList': _GPFA_NOTICE_TYPES,
        }
        payload = self._post_json(_GPFA_LIST_URL, body)
        if payload is None:
            return None

        if not payload.get('success'):
            logger.warning('[gdgpo] gpfa 列表接口返回异常: %s', payload.get('message'))
            return None

        data_obj = payload.get('data') or {}
        rows = data_obj.get('data') or []
        if not rows:
            return []

        # 注意：该接口对越界的 pageNum 不会返回空列表，而是照常返回数据（实测
        # page=7/8/9999 返回的record一样多），必须自己按 total 判断是否已翻完，
        # 否则 run() 的翻页循环永远不会自然终止，会在 max_pages 内重复抓相同数据
        total = data_obj.get('total')
        if isinstance(total, int) and (page - 1) * _PAGE_SIZE >= total:
            return []

        leads = []
        for row in rows:
            self._check_pause_and_stop()
            lead = self._gpfa_row_to_lead(row)
            detail = self._fetch_gpfa_detail(row.get('path'))
            if detail:
                lead.update(detail)
            leads.append(lead)

        logger.info('[gdgpo] gpfa 第 %d 页解析到 %d 条结果', page, len(leads))
        return leads

    def _post_json(self, url, json_body):
        """发起一次 POST JSON 请求（gpfa 列表接口用），带限速，失败返回 None"""
        if self.session is None:
            self._create_session()
        try:
            time.sleep(self.get_random_delay())
            headers = {
                'User-Agent': self.get_random_ua(),
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
            if self.referer:
                headers['Referer'] = self.referer
            response = self.session.post(url, json=json_body, headers=headers)
            if response.status_code != 200:
                logger.warning('[gdgpo] gpfa POST HTTP %d: %s', response.status_code, url)
                return None
            return response.json()
        except Exception as e:
            logger.warning('[gdgpo] gpfa POST 异常: %s - %s', url, e)
            return None

    def _fetch_gpfa_detail(self, path_url):
        """GET 征集公告静态详情页，提取全文文本、征集人/联系人/联系方式/地址、附件"""
        if not path_url:
            return {}

        response = self.fetch(path_url)
        if response is None:
            return {}

        html_text = response.text
        try:
            soup = BeautifulSoup(html_text, 'html.parser')
        except Exception:
            soup = BeautifulSoup(html_text, 'lxml')
        full_text = soup.get_text('\n', strip=True)

        detail = {}
        section_match = _GPFA_SECTION_RE.search(full_text)
        section_text = section_match.group(1) if section_match else full_text

        name = self._extract_gpfa_field(section_text, '征集人')
        person = self._extract_gpfa_field(section_text, '联系人')
        phone = self._extract_gpfa_field(section_text, '联系方式')
        addr = self._extract_gpfa_field(section_text, '联系地址')
        if name:
            detail['buyer_name'] = name[:200]
        if person:
            detail['contact_person'] = person[:50]
        if phone:
            detail['phone'] = phone[:50]
        if addr:
            detail['buyer_address'] = addr[:300]

        detail['attachments'] = self._extract_attachments(html_text)
        detail['_raw_html'] = html_text
        return detail

    @staticmethod
    def _extract_gpfa_field(section_text, label):
        """在"二、征集人信息"分段文本里按 '标签：值' 提取字段（取到该行换行为止）"""
        m = re.search(r'%s\s*[：:]\s*\n?\s*([^\n]+)' % re.escape(label), section_text)
        if not m:
            return None
        return m.group(1).strip() or None

    def _gpfa_row_to_lead(self, row):
        """把 gpfa 列表行映射为 Lead 字段字典"""
        lead = {
            'project_name': (row.get('projectName') or row.get('title') or '').strip()[:500],
            'bidding_number': (row.get('projectCode') or '').strip()[:100],
            'announcement_type': _GPFA_TYPE_NAME.get(row.get('typeCode'), row.get('typeCode') or ''),
            'region': (row.get('zoneName') or '').strip()[:50],
            'source_url': (row.get('path') or '').strip()[:500],
        }

        publish_date, publish_time = self._parse_datetime(row.get('publishTime') or row.get('createTime'))
        if publish_date:
            lead['publish_date'] = publish_date
        if publish_time:
            lead['publish_time'] = publish_time

        return {k: v for k, v in lead.items() if v not in (None, '')}

    # ------------------------------------------------------------------
    # gpfa 框架协议二次竞价采购公告（noticeGuid）
    # ------------------------------------------------------------------
    def _scrape_gpfa_xjj_page(self, page, notice_type=0, project_type=17, announcement_type=_GPFA_XJJ_ANNOUNCEMENT_TYPE):
        """采集 gpfa getNoticeList 接口下的某个子类型第 page 页

        该接口同时服务于二次竞价采购公告(noticeType=0)和二次竞价成交结果公告
        (noticeType=1)，只是 noticeType/projectType 参数不同，因此用参数化复用同一套代码。

        Returns:
            list[dict] 线索列表；None 表示请求失败；[] 表示该页无更多结果
        """
        params = {
            'regionGuid': '2137001',
            'noticeType': notice_type,
            'pageSize': _PAGE_SIZE,
            'pageNum': page,
            'webApp': 2,
            'upgradeRegionFlag': 'true',
        }
        if project_type is not None:
            params['projectType'] = project_type
        response = self.fetch(_GPFA_XJJ_LIST_URL, params=params, extra_headers={'Accept': 'application/json'})
        if response is None:
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning('[gdgpo] gpfa 二次竞价列表接口返回非JSON: %s', response.text[:200])
            return None

        if not payload.get('success'):
            logger.warning('[gdgpo] gpfa 二次竞价列表接口返回异常: %s', payload.get('message'))
            return None

        data_obj = payload.get('data') or {}
        rows = data_obj.get('data') or []
        if not rows:
            return []

        total = data_obj.get('total')
        if isinstance(total, int) and (page - 1) * _PAGE_SIZE >= total:
            return []

        leads = []
        for row in rows:
            self._check_pause_and_stop()
            lead = self._gpfa_xjj_row_to_lead(row, announcement_type)
            detail = self._fetch_gpfa_xjj_detail(row.get('noticeGuid'), announcement_type)
            if detail:
                lead.update(detail)
            leads.append(lead)

        logger.info('[gdgpo] gpfa noticeType=%s 第 %d 页解析到 %d 条结果', notice_type, page, len(leads))
        return leads

    def _fetch_gpfa_xjj_detail(self, notice_guid, announcement_type=_GPFA_XJJ_ANNOUNCEMENT_TYPE):
        """调用 getNoticeDetailExceptGD 获取详情（正文、联系人/联系方式、附件；
        成交结果类型还会多提取成交供应商/成交金额）

        Returns:
            dict: 补充/覆盖字段，请求失败时返回 {}
        """
        if not notice_guid:
            return {}

        response = self.fetch(
            _GPFA_XJJ_DETAIL_URL, params={'noticeGuid': notice_guid}, extra_headers={'Accept': 'application/json'}
        )
        if response is None:
            return {}

        try:
            payload = response.json()
        except ValueError:
            return {}

        if not payload.get('success'):
            return {}

        data = payload.get('data') or {}
        detail = {
            'project_name': (data.get('projectName') or data.get('title') or '').strip()[:500],
            'bidding_number': (data.get('projectNumber') or '').strip()[:100],
            'buyer_name': (data.get('orgName') or '').strip()[:200],
            'region': (data.get('regionName') or '').strip()[:50],
        }

        budget = self._parse_amount(data.get('budgetAmount'))
        if budget is not None:
            detail['budget_amount'] = budget

        deadline, _ = self._parse_datetime(data.get('endTime'))
        if deadline:
            detail['deadline'] = deadline

        content_html = data.get('content') or ''
        extra = {}
        if content_html:
            try:
                soup = BeautifulSoup(content_html, 'html.parser')
            except Exception:
                soup = BeautifulSoup(content_html, 'lxml')
            full_text = soup.get_text('\n', strip=True)
            person = self._extract_gpfa_field(full_text, '联系人')
            phone = self._extract_gpfa_field(full_text, '联系方式')
            if person:
                detail['contact_person'] = person[:50]
            if phone:
                detail['phone'] = phone[:50]

            # 成交结果公告(noticeType=1)专属：详情接口不返回 orgName/budgetAmount，
            # 需从正文里按标签提取采购人信息，并额外提取成交供应商/成交金额
            # （不在 Lead 现有字段里，放入 raw_data 保存，便于在详情页查看）
            if not detail.get('buyer_name'):
                buyer_name = self._extract_gpfa_field(full_text, '采购人名称')
                if buyer_name:
                    detail['buyer_name'] = buyer_name[:200]
            buyer_addr = self._extract_gpfa_field(full_text, '采购人地址')
            if buyer_addr:
                detail['buyer_address'] = buyer_addr[:300]
            if not detail.get('phone'):
                buyer_phone = self._extract_gpfa_field(full_text, '采购人联系方式')
                if buyer_phone:
                    detail['phone'] = buyer_phone[:50]

            winner_match = _GPFA_RESULT_WINNER_RE.search(full_text)
            if winner_match:
                extra['winning_supplier'] = winner_match.group(1).strip()[:200]
                extra['winning_supplier_address'] = winner_match.group(2).strip()[:300]
                try:
                    extra['winning_amount'] = float(winner_match.group(3).replace(',', ''))
                except ValueError:
                    pass

        detail = {k: v for k, v in detail.items() if v not in (None, '')}
        detail['announcement_type'] = announcement_type
        detail.update(extra)

        attachments = self._extract_attachments(content_html) if content_html else []
        # noticeFileList 是独立的附件字段列表，不一定嵌在 content 正文里
        for f in (data.get('noticeFileList') or []):
            url = f.get('fileUrl') or f.get('url') or ''
            if not url or any(a['url'] == url for a in attachments):
                continue
            attachments.append({'name': (f.get('fileName') or f.get('name') or 'attachment')[:200], 'url': url})
        detail['attachments'] = attachments
        if content_html:
            detail['_raw_html'] = content_html

        return detail

    def _gpfa_xjj_row_to_lead(self, row, announcement_type=_GPFA_XJJ_ANNOUNCEMENT_TYPE):
        """把 gpfa getNoticeList 列表行映射为 Lead 字段字典"""
        lead = {
            'project_name': (row.get('title') or '').strip()[:500],
            'announcement_type': announcement_type,
            'region': (row.get('regionName') or '').strip()[:50],
            'source_url': '%s?noticeGuid=%s' % (_GPFA_XJJ_PAGE_URL, row.get('noticeGuid', '')),
        }

        budget = self._parse_amount(row.get('budgetAmount'))
        if budget is not None:
            lead['budget_amount'] = budget

        publish_date, publish_time = self._parse_datetime(row.get('publishTime') or row.get('createDate'))
        if publish_date:
            lead['publish_date'] = publish_date
        if publish_time:
            lead['publish_time'] = publish_time

        return {k: v for k, v in lead.items() if v not in (None, '')}

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

