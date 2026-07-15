# -*- coding: utf-8 -*-
"""省级/市级生态环境部门建设项目环评公示采集。

普通地区继续解析服务端 HTML；广州受理公告通过公开 JSON API 获取，审批前和审批
公告仍解析静态 HTML；东莞通过官网 iframe 使用的公开表单接口获取列表，再读取公开
详情页。东莞第 4 页起要求验证码，因此只使用官网日期/受理号筛选，把每个结果分片
限制在前三页以内，不尝试识别或绕过验证码。珠海是纯静态的受理/审批前/审批后三个
栏目（走通用多栏目静态采集）；深圳是独立系统 ep.meeb.sz.gov.cn，列表为服务端渲染
的 .vm 页、详情为静态 htmltemp 页，均公开 GET；茂名为门户上的单一混排静态栏目。

公示中的联系人和电话属于生态环境主管部门，不是建设单位联系人，仅供项目真实性
核验。广州受理附件受图形验证码和每 IP 下载次数限制；东莞附件要求表单 POST，首期
均只保存源附件元数据，不交给 BaseScraper 的 GET 附件下载流程。
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode, urljoin

import httpx
from bs4 import BeautifulSoup

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# 数据源注册表：新增城市时在此追加一项即可复用同一套解析逻辑
# 新增条目必须包含 'level' 字段（值为 'province' 或 'city'），用于前端按省级/市级分组展示
REGIONS = {
    'guangdong': {
        'name': '广东省',
        'list_url': 'https://gdee.gd.gov.cn/jsxmsp3189/index.html',
        'page_url_pattern': 'https://gdee.gd.gov.cn/jsxmsp3189/index_{page}.html',
        'list_selector': 'ul.i_list',
        'level': 'province',
    },
    'jiangmen': {
        'name': '江门市',
        'list_url': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index.html',
        'page_url_pattern': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index_{page}.html',
        'list_selector': 'ul.infoList',
        'level': 'city',
    },
    'guangzhou': {
        'name': '广州市',
        'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpslgg/',
        'level': 'city',
        'adapter': 'guangzhou',
        'feeds': [
            {'type': 'gz_acceptance_api', 'announcement_type': '受理公告'},
            {
                'type': 'static',
                'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index.html',
                'page_url_pattern': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index_{page}.html',
                'list_selector': 'div.conts-list',
                'item_selector': True,
                'date_selector': 'span:last-child',
                'announcement_type': '审批前公示',
            },
            {
                'type': 'static',
                'list_url': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index.html',
                'page_url_pattern': 'https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index_{page}.html',
                'list_selector': 'div.conts-list',
                'item_selector': True,
                'date_selector': 'span:last-child',
                'announcement_type': '批复公告',
            },
        ],
    },
    'dongguan': {
        'name': '东莞市',
        'list_url': 'https://dgepb.dg.gov.cn/zwgk/jsxm/hpspxxgk/slqk/index.html',
        'level': 'city',
        'adapter': 'dongguan',
        'subject_id': '93e889f2501d3fe8015024305bdf0efc',
        'feeds': [
            {
                'dir_id': '402881204e959150014e959f42f30014',
                'date_field': 'HBTB_SLRQ',
                'announcement_type': '受理公告',
            },
            {
                'dir_id': '402881204e959150014e95a16630002c',
                'date_field': 'HBTB_GSSJ',
                'announcement_type': '审批前公示',
            },
            {
                'dir_id': '402881204e959150014e95bb85b5010f',
                'date_field': 'HBTB_GSSJ',
                'announcement_type': '批复公告',
            },
        ],
    },
    'zhuhai': {
        # 珠海市生态环境局“项目公示公告”是纯静态 HTML，受理/审批前/审批后分三个
        # 固定栏目（slgg/spqgs/sphgg），列表容器 div.wendangListC，日期在 <strong>，
        # 分页规律 index_{page}.html。无 adapter，走通用多栏目静态采集。
        'name': '珠海市',
        'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index.html',
        'level': 'city',
        'feeds': [
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/slgg/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '受理公告',
            },
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/spqgs/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/spqgs/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '审批前公示',
            },
            {
                'list_url': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/sphgg/index.html',
                'page_url_pattern': 'https://ssthjj.zhuhai.gov.cn/zxfw/xmgsgg/sphgg/index_{page}.html',
                'list_selector': 'div.wendangListC',
                'date_selector': 'strong',
                'announcement_type': '批复公告',
            },
        ],
    },
    'shenzhen': {
        # 深圳市生态环境局环评公示是独立系统 ep.meeb.sz.gov.cn:8443。列表为服务端
        # 渲染的 Velocity 页 approval_public_list/{gstype}.vm（gstype 1=受理/2=审批前/
        # 3=审批后），条目通过 doRead('<32位PKID>','<gstype>') 打开静态详情页
        # htmltemp/html/<PKID>_<gstype>.html。均为公开 GET，无登录/Cookie/签名。
        'name': '深圳市',
        'list_url': 'https://meeb.sz.gov.cn/xxgk/qt/gggs/hpgs/',
        'level': 'city',
        'adapter': 'shenzhen',
        'feeds': [
            {'gstype': 1, 'announcement_type': '受理公告'},
            {'gstype': 2, 'announcement_type': '审批前公示'},
            {'gstype': 3, 'announcement_type': '批复公告'},
        ],
    },
    # --- 以下为新增地级市（2026-07扩展） ---
    'heyuan': {
        'name': '河源市',
        'list_url': 'http://www.heyuan.gov.cn/zwgk/zdlyxx/hjbh/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'zhanjiang': {
        'name': '湛江市',
        'list_url': 'https://www.zhanjiang.gov.cn/zdlyxxgk/sthj/jsxmhjyx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'shaoguan': {
        'name': '韶关市',
        'list_url': 'https://www.sg.gov.cn/zw/zdlyxxgk/dzjg/sgssthjj/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'list_selector': 'div.pageList ul',
        'level': 'city',
    },
    'jieyang': {
        'name': '揭阳市',
        'list_url': 'http://www.jieyang.gov.cn/jyhbj/hjyw/jsxmhbslyspgs/index.html',
        'list_selector': 'ul#lmunes',
        'level': 'city',
    },
    'shanwei': {
        'name': '汕尾市',
        'list_url': 'https://www.shanwei.gov.cn/swhbj/459/515/zdly/hjbh03/index.html',
        'list_selector': 'div.newsclass ul',
        'level': 'city',
    },
    'yangjiang': {
        'name': '阳江市',
        'list_url': 'http://www.yangjiang.gov.cn/yj/zwgk/zdlyxxgk/hjbh/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',
        'level': 'city',
    },
    'shantou': {
        'name': '汕头市',
        'list_url': 'https://www.shantou.gov.cn/cnst/zdly/hjbhxxgk/index.html',
        'list_selector': 'div.list_div',
        'item_selector': True,  # 非ul/li结构，每个div.list_div直接作为条目
        'level': 'city',
    },
    'huizhou': {
        'name': '惠州市',
        'list_url': 'http://www.huizhou.gov.cn/zdlyxxgk/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'list_selector': 'ul.list',  # 与河源/湛江同一CMS模板，待实测确认
        'level': 'city',
    },
    'foshan': {
        'name': '佛山市',
        'list_url': 'http://sthj.foshan.gov.cn/hjyxpj/hpspgs/hpslgg/index.html',
        'list_selector': 'div.list-content2',
        'level': 'city',
    },
    'zhongshan': {
        'name': '中山市',
        'list_url': 'http://zsepb.zs.gov.cn/xxml/ztzl/gcjslyxmxx/ssthjjhpspgs/slgs/index.html',
        'list_selector': 'ul.pub_list',
        'level': 'city',
    },
    'yunfu': {
        'name': '云浮市',
        'list_url': 'https://www.yunfu.gov.cn/sthjj/zdlyxxgkzl/jsxmhjyxpj/slgg/index.html',
        'list_selector': 'div.nyrtct ul',
        'level': 'city',
    },
    'maoming': {
        # 茂名市门户”建设项目环境影响评价信息”是受理/审批前/审批后混排的单一栏目，
        # 容器 div.common-list，日期在 <span>，分页 index_{page}.html，公告类型按标题
        # 关键词分类（复用 _classify_category）。
        'name': '茂名市',
        'list_url': 'http://www.maoming.gov.cn/zwgk/zwzl/zdlyxxgkzl/hjbhxxgk/jsxmhjyxpjxx/index.html',
        'page_url_pattern': 'http://www.maoming.gov.cn/zwgk/zwzl/zdlyxxgkzl/hjbhxxgk/jsxmhjyxpjxx/index_{page}.html',
        'list_selector': 'div.common-list',
        'level': 'city',
    },
    'zhaoqing': {
        # 肇庆市生态环境局使用广东省标准 gkmlpt 信息公开目录 CMS。栏目树以 JSON
        # 嵌入 window._CONFIG.TREE，环评公示三个子栏目（受理公告/审批前公示/审批后公告）
        # 通过公开 GET JSON API /gkmlpt/api/all/{column_id} 获取列表。API 设计为单页
        # 全量模式（page≥2 返回 404），约 88-99 条/页，覆盖增量场景。详情页 HTML 内嵌
        # window._CONFIG.DETAIL JSON，含结构化表格和附件链接，无需登录/验证码。
        'name': '肇庆市',
        'list_url': 'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/index',
        'level': 'city',
        'adapter': 'zhaoqing',
        'feeds': [
            {'column_id': 21023, 'announcement_type': '受理公告'},
            {'column_id': 21025, 'announcement_type': '审批前公示'},
            {'column_id': 21028, 'announcement_type': '审批后公告'},
        ],
    },
    # --- 以下城市暂未接入（均因站点结构/反爬需要专门适配，非”没有页面”）---
    # 梅州: 门户 www.meizhou.gov.cn 对非浏览器请求返回 HTTP 521（Cloudflare 拦截），
    #       受理信息且多分散在兴宁/梅县/丰顺等分局，需专门处理反爬后再接入。
    # 清远: 门户 gdqy.gov.cn 返回 HTTP 412（需 JS/Cookie 校验），且环评审批多下放到
    #       英德/清新/佛冈/连南等分局，市本级缺独立受理列表。
    # 潮州: 市局 chaozhou.gov.cn 无独立受理公告栏目，受理信息主要在潮安/饶平分局，
    #       需按分局聚合，暂缓。
}

_ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|doc|docx|xls|xlsx|zip|rar|7z|txt)(\?|$)', re.IGNORECASE)

_GUANGZHOU_API_BASE = 'http://112.94.69.56:8066'
_GUANGZHOU_LIST_URL = _GUANGZHOU_API_BASE + '/api/hpslgl/getListPublished'
_GUANGZHOU_DETAIL_URL = _GUANGZHOU_API_BASE + '/api/hpslgl/detail'
_GUANGZHOU_DETAIL_PAGE = _GUANGZHOU_API_BASE + '/#/hpslzs/index'
_GUANGZHOU_PAGE_SIZE = 100

_DONGGUAN_LIST_URL = 'https://dgstsjzx.dg.cn/hbgs/zwgk/item.do'
_DONGGUAN_DETAIL_URL = 'https://dgstsjzx.dg.cn/hbgs/zwgk/view.do'
_DONGGUAN_PAGE_SIZE = 20
_DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA = 3
_DONGGUAN_MAX_RESULTS_PER_SLICE = _DONGGUAN_PAGE_SIZE * _DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA
# 实测 HBTB_XH 是不超过 11 位的数字受理号。单日超过 60 条时先用这个完整
# 数字域做一次守恒校验；若存在空值、非数字或域外值，筛选总量会少于未筛选
# 总量，采集器会失败报警，而不是静默漏数。
_DONGGUAN_NUMBER_MIN = 0
_DONGGUAN_NUMBER_MAX = 99_999_999_999
_DONGGUAN_MAX_SPLIT_DEPTH = 48

_SHENZHEN_BASE = 'https://ep.meeb.sz.gov.cn:8443'
_SHENZHEN_LIST_URL = _SHENZHEN_BASE + '/HP_SZ_OUT/publicity/approval_public_list/{gstype}.vm'
_SHENZHEN_DETAIL_URL = _SHENZHEN_BASE + '/HP_SZ_OUT/htmltemp/html/{pkid}_{gstype}.html'
_SHENZHEN_PAGE_SIZE = 10
_SHENZHEN_DOREAD_RE = re.compile(r"doRead\('([0-9a-fA-F]{32})'\s*,\s*'(\d+)'\)")

_ZHAOQING_APP_URL = 'https://www.zhaoqing.gov.cn/zqhjj'
_ZHAOQING_API_URL = _ZHAOQING_APP_URL + '/gkmlpt/api/all/{column_id}?page=1&sid=758019'
_ZHAOQING_DETAIL_RE = re.compile(r'DETAIL:\s*({.*?})\s*,\s*TREE:')
# 首次全量阈值：DB 中肇庆 lead 达到此数才切换到增量模式。
# 三栏目合计约 487 条（受理203+审批前156+审批后128），设为 50 保证首次
# 即使中途只入库了几条也会继续全量直到真正完整。
_ZHAOQING_FULL_THRESHOLD = 50


class EiaScraper(BaseScraper):
    source_type = 'eia'
    base_url = 'https://gdee.gd.gov.cn/jsxmsp3189/'

    def __init__(self, app=None):
        super().__init__(app=app)
        self.dongguan_lookback_days = 2
        self.zhaoqing_lookback_days = 3
        self.anti_scrape_wait = 0
        self._guangzhou_total = None
        self._guangzhou_seen_ids = set()
        if app is not None:
            self.delay_min = app.config.get('EIA_DELAY_MIN', self.delay_min)
            self.delay_max = app.config.get('EIA_DELAY_MAX', self.delay_max)
            self.anti_scrape_wait = app.config.get('EIA_ANTI_SCRAPE_WAIT', 0)
            self.dongguan_lookback_days = max(
                1, int(app.config.get('EIA_DONGGUAN_LOOKBACK_DAYS', self.dongguan_lookback_days))
            )
            self.zhaoqing_lookback_days = max(
                1, int(app.config.get('EIA_ZHAOQING_LOOKBACK_DAYS', self.zhaoqing_lookback_days))
            )

    def default_keywords(self):
        """生成默认的 "region:地区代码" 伪关键词，覆盖所有已配置数据源"""
        return [f'region:{key}' for key in REGIONS]

    def _keyword_display(self, keyword):
        """将 region:xxx 伪关键词转换为地区名称用于进度展示。"""
        if keyword.startswith('region:'):
            region_key = keyword.split(':', 1)[1]
            region = REGIONS.get(region_key)
            return region['name'] if region else keyword
        return keyword

    def run(self, keywords=None, max_pages=5):
        if not keywords:
            keywords = self.default_keywords()
        return super().run(keywords=keywords, max_pages=max_pages)

    def _scrape_page(self, keyword, page):
        region_key = keyword.split(':', 1)[1] if keyword.startswith('region:') else None
        region = REGIONS.get(region_key)
        if region is None:
            logger.error('[eia] 无效的地区代码: %s', keyword)
            return None

        adapter = region.get('adapter')
        if adapter == 'guangzhou':
            result = self._scrape_guangzhou_page(region, page)
        elif adapter == 'dongguan':
            result = self._scrape_dongguan_page(region, page)
        elif adapter == 'shenzhen':
            result = self._scrape_shenzhen_page(region, page)
        elif adapter == 'zhaoqing':
            result = self._scrape_zhaoqing_page(region, page)
        elif region.get('feeds'):
            result = self._scrape_static_feeds(region, page)
        else:
            result = self._scrape_static_page(region, page)
        return result

    def _scrape_static_feeds(self, region, page):
        """采集由多个纯静态 HTML 栏目组成的地区（如珠海受理/审批前/审批后三栏）。"""
        results = []
        for feed in region['feeds']:
            rows = self._scrape_static_page(
                feed,
                page,
                region_name=region['name'],
                announcement_type=feed.get('announcement_type'),
            )
            if rows is None:
                return None
            results.extend(rows)
        return results

    def _scrape_static_page(self, source, page, region_name=None, announcement_type=None):
        """采集一个静态 HTML feed，兼容原有地区与广州两个固定分类栏目。"""
        if page == 1:
            list_url = source['list_url']
        else:
            page_pattern = source.get('page_url_pattern')
            if not page_pattern:
                page_pattern = source['list_url'].replace('index.html', 'index_{page}.html')
            list_url = page_pattern.format(page=page)
        _, soup, status_code = self._fetch_html_with_status(list_url)
        if status_code == 404:
            if page > 1:
                return []
            logger.error('[eia] 静态栏目首页不存在，可能已迁移: %s', list_url)
            return None
        if soup is None:
            logger.error('[eia] 静态列表请求失败: %s', list_url)
            return None

        containers = soup.select(source['list_selector'])
        if not containers:
            logger.error('[eia] 静态列表 selector 失效: %s - %s', list_url, source['list_selector'])
            return None
        # 支持非ul/li结构：若配置了item_selector，list_selector直接选择条目元素
        if source.get('item_selector'):
            items = containers
        else:
            main_ul = max(containers, key=lambda u: len(u.find_all('li')))
            items = main_ul.find_all('li')
        if not items:
            return []

        results = []
        for item_node in items:
            self._check_pause_and_stop()
            a = item_node.find('a')
            if a is None or not a.get('href'):
                continue
            detail_url = urljoin(list_url, a['href'])
            title = (a.get('title') or a.get_text(strip=True)).strip()
            date_node = item_node.select_one(source.get('date_selector', 'span'))
            publish_date = self._parse_date(date_node.get_text(strip=True) if date_node else '')
            item_type = announcement_type or source.get('announcement_type') or self._classify_category(title)

            detail_html, detail_soup, detail_status = self._fetch_html_with_status(detail_url)
            if detail_status == 404:
                logger.warning('[eia] 静态详情已下线，保留列表核心字段: %s', detail_url)
                results.append({
                    'project_name': title,
                    'announcement_type': item_type,
                    'region': region_name or source['name'],
                    'publish_date': publish_date,
                    'source_url': detail_url,
                })
                continue
            if detail_soup is None:
                logger.error('[eia] 静态详情请求失败: %s', detail_url)
                return None

            item = self._parse_detail(detail_soup)
            item['project_name'] = item.get('project_name') or title
            item['announcement_type'] = item_type
            item['region'] = region_name or source['name']
            item['publish_date'] = publish_date
            item['source_url'] = detail_url
            item['attachments'] = self._extract_attachments(detail_soup, detail_url)
            item['_raw_html'] = detail_html
            results.append(item)

        return results

    def _fetch_html_with_status(self, url):
        """返回 HTML、soup、状态码；网络错误与 HTTP 错误不再混成空列表。"""
        response = self.fetch(url, return_error_response=True)
        if response is None:
            return None, None, None
        if response.status_code != 200:
            return None, None, response.status_code
        html_text = response.text
        try:
            soup = BeautifulSoup(html_text, 'lxml')
        except Exception:
            soup = BeautifulSoup(html_text, 'html.parser')
        return html_text, soup, response.status_code

    # ------------------------------------------------------------------
    # 广州：受理 JSON API + 两个静态 HTML feed
    # ------------------------------------------------------------------
    def _scrape_guangzhou_page(self, region, page):
        if page == 1:
            self._guangzhou_total = None
            self._guangzhou_seen_ids.clear()
        results = []
        for feed in region['feeds']:
            if feed['type'] == 'gz_acceptance_api':
                rows = self._scrape_guangzhou_acceptance_page(page)
            else:
                rows = self._scrape_static_page(
                    feed,
                    page,
                    region_name=region['name'],
                    announcement_type=feed['announcement_type'],
                )
            if rows is None:
                return None
            results.extend(rows)
        return results

    def _scrape_guangzhou_acceptance_page(self, page):
        params = {
            'PROJECT_NAME': '',
            'CONSTRUCTION_UNIT': '',
            'pageNum': page,
            'pageSize': _GUANGZHOU_PAGE_SIZE,
        }
        response = self.fetch(
            _GUANGZHOU_LIST_URL,
            params=params,
            extra_headers={'Accept': 'application/json'},
        )
        if response is None:
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.error('[eia] 广州受理列表返回非 JSON: %s', response.text[:200])
            return None

        data = payload.get('data') if isinstance(payload, dict) else None
        rows = data.get('list') if isinstance(data, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get('code') not in (0, '0')
            or not isinstance(rows, list)
        ):
            logger.error('[eia] 广州受理列表 schema 异常: %s', str(payload)[:300])
            return None

        total = data.get('total')
        try:
            total = int(total)
        except (TypeError, ValueError):
            logger.error('[eia] 广州受理列表 total 无效: %r', total)
            return None
        if self._guangzhou_total is None:
            self._guangzhou_total = total
        elif total != self._guangzhou_total:
            logger.error(
                '[eia] 广州受理抓取期间 total 变化: %d -> %d',
                self._guangzhou_total,
                total,
            )
            return None
        if (page - 1) * _GUANGZHOU_PAGE_SIZE >= total:
            return []

        expected_count = min(
            _GUANGZHOU_PAGE_SIZE,
            total - (page - 1) * _GUANGZHOU_PAGE_SIZE,
        )
        if len(rows) != expected_count:
            logger.error(
                '[eia] 广州受理第 %d 页数量不守恒，期望 %d 条，实际 %d 条',
                page,
                expected_count,
                len(rows),
            )
            return None
        record_ids = []
        for row in rows:
            if not isinstance(row, dict) or not str(row.get('ID') or '').strip():
                logger.error('[eia] 广州受理第 %d 页存在无效记录', page)
                return None
            record_ids.append(str(row['ID']).strip())
        if len(set(record_ids)) != len(record_ids):
            logger.error('[eia] 广州受理第 %d 页存在重复 ID', page)
            return None
        repeated_ids = self._guangzhou_seen_ids.intersection(record_ids)
        if repeated_ids:
            logger.error('[eia] 广州受理跨页出现重复 ID: %s', sorted(repeated_ids)[:5])
            return None

        results = []
        for row in rows:
            self._check_pause_and_stop()
            merged = dict(row)
            record_id = merged.get('ID')
            # 列表接口当前已返回核心字段和附件元数据。仅在字段缺失时调用详情
            # POST，避免定时任务为每条记录增加一次无必要请求。
            if record_id and (
                not merged.get('PROJECT_NAME')
                or not merged.get('CONSTRUCTION_UNIT')
                or not merged.get('CONSTRUCTION_LOCATION')
                or not merged.get('ENV_ASSESSMENT_UNIT')
                or not (merged.get('PUBLISH_DATE') or merged.get('ACCEPTANCE_DATE'))
                or merged.get('FILELIST') is None
            ):
                detail = self._fetch_guangzhou_detail(record_id)
                if detail:
                    merged.update({k: v for k, v in detail.items() if v not in (None, '')})
            required_fields = (
                'PROJECT_NAME',
                'CONSTRUCTION_UNIT',
                'CONSTRUCTION_LOCATION',
                'ENV_ASSESSMENT_UNIT',
            )
            publish_value = merged.get('PUBLISH_DATE') or merged.get('ACCEPTANCE_DATE')
            if any(not str(merged.get(field) or '').strip() for field in required_fields) or (
                self._parse_date(publish_value) is None
            ):
                logger.error('[eia] 广州受理核心字段补全失败，ID=%s', record_id)
                return None
            results.append(self._guangzhou_row_to_lead(merged))

        self._guangzhou_seen_ids.update(record_ids)
        logger.info('[eia] 广州受理第 %d 页解析到 %d 条结果', page, len(results))
        return results

    def _fetch_guangzhou_detail(self, record_id):
        payload = self._post_json(_GUANGZHOU_DETAIL_URL, {'id': str(record_id)})
        if payload is None:
            return None
        data = payload.get('data') if isinstance(payload, dict) else None
        if payload.get('code') not in (0, '0') or not isinstance(data, dict):
            logger.warning('[eia] 广州受理详情 schema 异常，ID=%s', record_id)
            return None
        return data

    def _guangzhou_row_to_lead(self, row):
        record_id = str(row.get('ID') or '').strip()
        remark = str(row.get('REMARK') or '').strip()
        phone = self._extract_government_phone(remark)
        source_files = self._parse_source_files(row.get('FILELIST'), f'广州 ID={record_id}')
        source_url = (
            f'{_GUANGZHOU_DETAIL_PAGE}?id={quote(record_id, safe="")}'
            if record_id else REGIONS['guangzhou']['list_url']
        )
        return {
            'project_name': str(row.get('PROJECT_NAME') or '').strip()[:500],
            'buyer_name': str(row.get('CONSTRUCTION_UNIT') or '').strip()[:200],
            'buyer_address': str(row.get('CONSTRUCTION_LOCATION') or '').strip()[:300],
            'agency_name': str(row.get('ENV_ASSESSMENT_UNIT') or '').strip()[:200],
            'phone': phone[:50],
            'publish_date': self._parse_date(row.get('PUBLISH_DATE') or row.get('ACCEPTANCE_DATE')),
            'announcement_type': '受理公告',
            'region': '广州市',
            'source_url': source_url,
            'source_record_id': record_id,
            'source_files': source_files,
            'environment_document_type': row.get('ENV_DOC_TYPE') or '',
            'acceptance_time': row.get('ACCEPTANCE_DATE') or '',
            'source_publish_time': row.get('PUBLISH_DATE') or '',
            'source_remark': remark,
            'government_contact_role': '生态环境主管部门公众咨询电话' if phone else '',
        }

    # ------------------------------------------------------------------
    # 深圳：服务端渲染 .vm 列表 + 静态 htmltemp 详情页，均为公开 GET
    # ------------------------------------------------------------------
    def _scrape_shenzhen_page(self, region, page):
        results = []
        for feed in region['feeds']:
            rows = self._scrape_shenzhen_feed_page(feed, page)
            if rows is None:
                return None
            results.extend(rows)
        return results

    def _scrape_shenzhen_feed_page(self, feed, page):
        gstype = feed['gstype']
        list_url = _SHENZHEN_LIST_URL.format(gstype=gstype)
        response = self.fetch(
            list_url,
            params={'pageNum': page, 'pageSize': _SHENZHEN_PAGE_SIZE},
            extra_headers={'Accept': 'text/html,application/xhtml+xml'},
        )
        if response is None:
            return None
        try:
            soup = BeautifulSoup(response.text, 'lxml')
        except Exception:
            soup = BeautifulSoup(response.text, 'html.parser')

        total_pages = self._shenzhen_total_pages(soup)
        if total_pages is not None and page > total_pages:
            return []

        nodes = [
            node for node in soup.select('div.form-group')
            if node.find('a', attrs={'onclick': _SHENZHEN_DOREAD_RE})
        ]
        results = []
        for node in nodes:
            self._check_pause_and_stop()
            a = node.find('a', attrs={'onclick': _SHENZHEN_DOREAD_RE})
            match = _SHENZHEN_DOREAD_RE.search(a.get('onclick') or '')
            if not match:
                continue
            pkid, gs = match.group(1), match.group(2)
            title = a.get_text(strip=True)
            date_node = node.select_one('p.form-control-static') or node.select_one('.col-sm-2')
            publish_date = self._parse_date(date_node.get_text(strip=True) if date_node else '')
            detail_url = _SHENZHEN_DETAIL_URL.format(pkid=pkid, gstype=gs)
            lead = {
                'project_name': title,
                'announcement_type': feed['announcement_type'],
                'region': '深圳市',
                'publish_date': publish_date,
                'source_url': detail_url,
                'source_record_id': pkid,
            }
            detail_html, detail_soup, detail_status = self._fetch_html_with_status(detail_url)
            if detail_status == 404:
                logger.warning('[eia] 深圳详情已下线，保留列表核心字段: %s', detail_url)
            elif detail_soup is None:
                logger.error('[eia] 深圳详情请求失败: %s', detail_url)
                return None
            else:
                detail = {
                    key: value for key, value in self._parse_shenzhen_detail(detail_soup).items()
                    if value not in (None, '')
                }
                lead.update(detail)
                lead['_raw_html'] = detail_html
            results.append(lead)
        logger.info('[eia] 深圳 gstype=%s 第 %d 页解析到 %d 条结果', gstype, page, len(results))
        return results

    @staticmethod
    def _shenzhen_total_pages(soup):
        el = soup.find('input', attrs={'name': 'pages'})
        if el is not None and str(el.get('value') or '').isdigit():
            return int(el['value'])
        return None

    def _parse_shenzhen_detail(self, soup):
        """深圳详情页表格是「2 格行 + 4 格行」混排，按“标签以：结尾→取下一格为值”成对解析。"""
        kv = {}
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                texts = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                i = 0
                while i + 1 < len(texts):
                    if texts[i].endswith(('：', ':')):
                        kv[texts[i].rstrip('：:').strip()] = texts[i + 1]
                        i += 2
                    else:
                        i += 1
        full_text = soup.get_text('\n', strip=True)
        phone = self._extract_government_phone(full_text)
        source_files = []
        for a in soup.find_all('a', href=True):
            name = a.get_text(strip=True)
            if name and _ATTACHMENT_EXT_RE.search(name):
                source_files.append({'name': name, 'url': urljoin(_SHENZHEN_BASE, a['href'])})
        result = {
            'project_name': (kv.get('项目名称') or '').strip(),
            'buyer_name': (kv.get('建设单位名称') or kv.get('建设单位') or '').strip(),
            'buyer_address': (kv.get('建设地点') or '').strip(),
            'agency_name': (kv.get('环评机构名称') or kv.get('环评机构') or '').strip(),
        }
        if phone:
            result['phone'] = phone
            result['government_contact_role'] = '生态环境主管部门公众咨询电话'
        if kv.get('受理日期'):
            result['acceptance_time'] = kv['受理日期']
        if kv.get('环评文件类型'):
            result['environment_document_type'] = kv['环评文件类型']
        if source_files:
            result['source_files'] = source_files
        return result

    # ------------------------------------------------------------------
    # 东莞：公开 POST 列表 + GET 详情，严格停留在第 1～3 页
    # ------------------------------------------------------------------
    def _scrape_dongguan_page(self, region, page):
        # BaseScraper 仍按逻辑页循环；东莞在第一页内部完成日期/受理号分片，
        # 后续逻辑页立即结束，绝不把 page=4 传给网站。
        if page > 1:
            return []
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=self.dongguan_lookback_days - 1)
        return self._scrape_dongguan_window(region, start_date, end_date)

    def _scrape_dongguan_window(self, region, start_date, end_date):
        raw_records = []
        seen = set()
        for feed in region['feeds']:
            rows = self._fetch_dongguan_feed(region, feed, start_date, end_date)
            if rows is None:
                return None
            for row in rows:
                record_key = (feed['dir_id'], str(row['ID']).strip())
                if record_key in seen:
                    continue
                seen.add(record_key)
                raw_records.append((feed, row))

        related_by_number = {}
        for _, row in raw_records:
            acceptance_number = str(row.get('HBTB_XH') or '').strip()
            if acceptance_number and row.get('HBTB_JSDW'):
                related_by_number[acceptance_number] = row
        related_lookup_cache = {}

        leads = []
        for feed, row in raw_records:
            self._check_pause_and_stop()
            merged_row = dict(row)
            acceptance_number = str(merged_row.get('HBTB_XH') or '').strip()
            related = related_by_number.get(acceptance_number)
            if (
                related is None
                and acceptance_number
                and feed['announcement_type'] != '受理公告'
                and not merged_row.get('HBTB_JSDW')
            ):
                if acceptance_number not in related_lookup_cache:
                    related_lookup_cache[acceptance_number] = self._fetch_dongguan_acceptance_by_number(
                        region,
                        acceptance_number,
                        merged_row.get('HBTB_XMMC'),
                    )
                related = related_lookup_cache[acceptance_number]
                if related is None:
                    return None
            if related is not None:
                for field in ('HBTB_JSDW', 'HBTB_JSDD', 'HBTB_HPJG'):
                    if not merged_row.get(field) and related.get(field):
                        merged_row[field] = related[field]
            lead = self._dongguan_row_to_lead(region, feed, merged_row)
            detail_html, detail_soup, detail_status = self._fetch_html_with_status(lead['source_url'])
            if detail_status == 404:
                logger.warning('[eia] 东莞详情已下线，保留列表核心字段: %s', lead['source_url'])
            elif detail_soup is None:
                logger.error('[eia] 东莞详情请求失败: %s', lead['source_url'])
                return None
            elif not self._validate_dongguan_detail(detail_soup, feed, merged_row):
                logger.error('[eia] 东莞详情模板或记录身份异常: %s', lead['source_url'])
                return None
            else:
                detail = {
                    key: value for key, value in self._parse_detail(detail_soup).items()
                    if value not in (None, '')
                }
                lead.update(detail)
                lead['_raw_html'] = detail_html
            leads.append(lead)

        logger.info(
            '[eia] 东莞 %s 至 %s 共解析到 %d 条结果', start_date, end_date, len(leads)
        )
        return leads

    def _validate_dongguan_detail(self, soup, feed, row):
        kv = self._extract_kv_tables(soup)
        project_name = re.sub(r'\s+', '', str(row.get('HBTB_XMMC') or ''))
        detail_name = re.sub(r'\s+', '', str(kv.get('项目名称') or ''))
        if not project_name or detail_name != project_name:
            return False

        acceptance_number = re.sub(r'\s+', '', str(row.get('HBTB_XH') or ''))
        detail_number = re.sub(r'\s+', '', str(kv.get('受理号') or ''))
        if detail_number and acceptance_number and detail_number != acceptance_number:
            return False

        required_by_type = {
            '受理公告': ('建设单位', '建设地点'),
            '审批前公示': ('建设单位', '建设地点'),
            '批复公告': ('审批文号',),
        }
        required_fields = required_by_type.get(feed['announcement_type'], ())
        if feed['announcement_type'] == '批复公告' and not kv.get('审批文号'):
            required_fields = ('批复文号',)
        return all(str(kv.get(field) or '').strip() for field in required_fields)

    def _fetch_dongguan_acceptance_by_number(self, region, acceptance_number, project_name):
        """用官网精确受理号查询历史受理记录，补全跨日期阶段的建设单位等字段。"""
        acceptance_feed = next(
            feed for feed in region['feeds'] if feed['announcement_type'] == '受理公告'
        )
        form = {
            'page': '1',
            'rows': str(_DONGGUAN_PAGE_SIZE),
            'dirId': acceptance_feed['dir_id'],
            'subjectId': region['subject_id'],
            'captchaId': '',
            'HBTB_XH': str(acceptance_number),
            'HBTB_XH_END': str(acceptance_number),
            'HBTB_XMMC': '',
            'HBTB_JSDD': '',
            'HBTB_JSDW': '',
            acceptance_feed['date_field']: '',
            acceptance_feed['date_field'] + '_END': '',
        }
        payload = self._post_form(_DONGGUAN_LIST_URL, form)
        if payload is None:
            return None
        if payload['total'] > _DONGGUAN_PAGE_SIZE or len(payload['rows']) != payload['total']:
            logger.error(
                '[eia] 东莞精确受理号查询数量异常: %s，total=%d，rows=%d',
                acceptance_number,
                payload['total'],
                len(payload['rows']),
            )
            return None

        candidates = [
            row for row in payload['rows']
            if str(row.get('HBTB_XH') or '').strip() == str(acceptance_number)
        ]
        normalized_name = str(project_name or '').strip()
        for row in candidates:
            if normalized_name and str(row.get('HBTB_XMMC') or '').strip() == normalized_name:
                return row
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            logger.warning('[eia] 东莞受理号关联存在歧义，未自动补全: %s', acceptance_number)
        return {}

    def _fetch_dongguan_feed(
        self,
        region,
        feed,
        start_date,
        end_date,
        number_start=None,
        number_end=None,
        depth=0,
    ):
        if depth > _DONGGUAN_MAX_SPLIT_DEPTH:
            logger.error('[eia] 东莞分片递归超过安全深度: %s 至 %s', start_date, end_date)
            return None

        first = self._request_dongguan_page(
            region, feed, start_date, end_date, 1, number_start, number_end
        )
        if first is None:
            return None
        total = first['total']

        if total <= _DONGGUAN_MAX_RESULTS_PER_SLICE:
            rows = list(first['rows'])
            page_count = (total + _DONGGUAN_PAGE_SIZE - 1) // _DONGGUAN_PAGE_SIZE
            for page in range(2, page_count + 1):
                payload = self._request_dongguan_page(
                    region, feed, start_date, end_date, page, number_start, number_end
                )
                if payload is None:
                    return None
                if payload['total'] != total:
                    logger.error(
                        '[eia] 东莞分片抓取期间 total 变化: %d -> %d', total, payload['total']
                    )
                    return None
                rows.extend(payload['rows'])
            rows = self._deduplicate_dongguan_rows(rows)
            if len(rows) != total:
                logger.error(
                    '[eia] 东莞分片数量不守恒，期望 %d 条，实际唯一记录 %d 条',
                    total,
                    len(rows),
                )
                return None
            return rows

        if start_date < end_date and number_start is None and number_end is None:
            midpoint = start_date + timedelta(days=(end_date - start_date).days // 2)
            newer = self._fetch_dongguan_feed(
                region, feed, midpoint + timedelta(days=1), end_date, depth=depth + 1
            )
            if newer is None:
                return None
            older = self._fetch_dongguan_feed(
                region, feed, start_date, midpoint, depth=depth + 1
            )
            if older is None:
                return None
            merged = self._deduplicate_dongguan_rows(newer + older)
            if len(merged) != total:
                logger.error(
                    '[eia] 东莞日期分片数量不守恒，期望 %d 条，实际 %d 条', total, len(merged)
                )
                return None
            return merged

        if number_start is None or number_end is None:
            bounded = self._fetch_dongguan_feed(
                region,
                feed,
                start_date,
                end_date,
                _DONGGUAN_NUMBER_MIN,
                _DONGGUAN_NUMBER_MAX,
                depth + 1,
            )
            if bounded is None:
                return None
            if len(bounded) != total:
                logger.error(
                    '[eia] 东莞受理号全域未覆盖全部记录，未筛选 %d 条，数字域内 %d 条',
                    total,
                    len(bounded),
                )
                return None
            return bounded

        try:
            low, high = int(number_start), int(number_end)
        except (TypeError, ValueError):
            logger.error(
                '[eia] 东莞受理号范围无效: %r-%r', number_start, number_end
            )
            return None
        if low >= high:
            logger.error(
                '[eia] 东莞同一受理号范围仍超过 %d 条，无法合规继续拆分: %s-%s',
                _DONGGUAN_MAX_RESULTS_PER_SLICE,
                low,
                high,
            )
            return None

        midpoint = (low + high) // 2
        newer = self._fetch_dongguan_feed(
            region,
            feed,
            start_date,
            end_date,
            midpoint + 1,
            high,
            depth + 1,
        )
        if newer is None:
            return None
        older = self._fetch_dongguan_feed(
            region,
            feed,
            start_date,
            end_date,
            low,
            midpoint,
            depth + 1,
        )
        if older is None:
            return None
        merged = self._deduplicate_dongguan_rows(newer + older)
        if len(merged) != total:
            logger.error(
                '[eia] 东莞受理号分片数量不守恒，期望 %d 条，实际 %d 条', total, len(merged)
            )
            return None
        return merged

    def _request_dongguan_page(
        self, region, feed, start_date, end_date, page, number_start=None, number_end=None
    ):
        if page < 1 or page > _DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA:
            raise ValueError('东莞列表只允许请求第 1～3 页')
        form = {
            'page': str(page),
            'rows': str(_DONGGUAN_PAGE_SIZE),
            'dirId': feed['dir_id'],
            'subjectId': region['subject_id'],
            'captchaId': '',
            'HBTB_XH': '' if number_start is None else str(number_start),
            'HBTB_XH_END': '' if number_end is None else str(number_end),
            'HBTB_XMMC': '',
            'HBTB_JSDD': '',
            'HBTB_JSDW': '',
            feed['date_field']: start_date.strftime('%Y-%m-%d'),
            feed['date_field'] + '_END': end_date.strftime('%Y-%m-%d'),
        }
        return self._post_form(_DONGGUAN_LIST_URL, form)

    @staticmethod
    def _deduplicate_dongguan_rows(rows):
        result = []
        seen = set()
        for row in rows:
            record_id = str(row.get('ID') or '')
            key = record_id or str(row.get('HBTB_XH') or '') + str(row.get('HBTB_XMMC') or '')
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _dongguan_row_to_lead(self, region, feed, row):
        record_id = str(row.get('ID') or '').strip()
        source_url = _DONGGUAN_DETAIL_URL + '?' + urlencode({
            'dirId': feed['dir_id'],
            'id': record_id,
            'subjectId': region['subject_id'],
        })
        source_files = self._parse_source_files(
            row.get('HBTB_HPWJ') or row.get('HBTB_PFWJ'),
            f'东莞 ID={record_id}',
        )
        phone = str(row.get('HBTB_LXDH') or '').strip()
        publish_value = row.get(feed['date_field']) or row.get('ADDTIME')
        return {
            'project_name': str(row.get('HBTB_XMMC') or '').strip()[:500],
            'buyer_name': str(row.get('HBTB_JSDW') or '').strip()[:200],
            'buyer_address': str(row.get('HBTB_JSDD') or '').strip()[:300],
            'agency_name': str(row.get('HBTB_HPJG') or '').strip()[:200],
            'phone': phone[:50],
            'publish_date': self._parse_date(publish_value),
            'announcement_type': feed['announcement_type'],
            'region': region['name'],
            'source_url': source_url,
            'source_record_id': record_id,
            'source_dir_id': feed['dir_id'],
            'acceptance_number': str(row.get('HBTB_XH') or '').strip(),
            'source_files': source_files,
            'approval_number': row.get('HBTB_SPWH') or '',
            'approval_file_name': row.get('HBTB_WJMC') or '',
            'project_summary': row.get('HBTB_XMGK') or '',
            'environmental_impacts_and_measures': row.get('HBTB_ZYHJYXJYFHZJQBLHJYXDDCHCS') or '',
            'public_participation': row.get('HBTB_GZCYQK') or '',
            'environmental_commitment': row.get('HBTB_XGHBCSCN') or '',
            'preliminary_approval_opinion': row.get('HBTB_NBYPZDYY') or '',
            'government_contact_name': row.get('HBTB_LXR') or '',
            'government_contact_phone': phone,
            'government_contact_address': row.get('HBTB_TXDZ') or '',
            'government_contact_role': '生态环境主管部门公众咨询电话' if phone else '',
            'source_remark': row.get('HBTB_BZ') or '',
            'source_publish_time': publish_value or '',
            'source_updated_time': row.get('UPDATETIME') or '',
        }

    # ------------------------------------------------------------------
    # 肇庆：gkmlpt 公开 GET JSON API + HTML 详情页内嵌 DETAIL JSON
    # ------------------------------------------------------------------
    def _zhaoqing_start_date(self, region_name):
        """首次全量 / 后续增量策略：
        DB 中肇庆 lead 少于 _ZHAOQING_FULL_THRESHOLD → 仍为首次，全量采集（不过滤日期）；
        达到阈值 → 仅取最近 zhaoqing_lookback_days 天（增量窗口）。
        这避免了只采集到几条记录就误判为已全量的问题。
        """
        threshold = _ZHAOQING_FULL_THRESHOLD
        if self.app is not None:
            try:
                from app.models import Lead
                with self.app.app_context():
                    count = Lead.query.filter(
                        Lead.source_type == 'eia',
                        Lead.region == region_name,
                    ).count()
                if count >= threshold:
                    logger.info('[eia] 肇庆已有 %d 条历史数据(≥%d)，使用 %d 天增量窗口',
                                count, threshold, self.zhaoqing_lookback_days)
                    return datetime.now().date() - timedelta(days=self.zhaoqing_lookback_days)
                else:
                    logger.info('[eia] 肇庆仅 %d 条历史数据(<%d)，全量抓取（无日期过滤）',
                                count, threshold)
                    return None
            except Exception as exc:
                logger.warning('[eia] 肇庆 DB 查询异常，回退到增量窗口: %s', exc)
        # 无 app 上下文（测试场景）时默认走增量窗口
        return datetime.now().date() - timedelta(days=self.zhaoqing_lookback_days)

    def _scrape_zhaoqing_page(self, region, page):
        # gkmlpt API 为单页全量模式（page≥2 返回 404），类似东莞在第一页内完成
        # 所有采集，后续逻辑页立即结束。
        if page > 1:
            return []

        # 首次全量 / 后续增量：DB 中无肇庆 lead 时全量采集，否则走 lookback 窗口。
        start_date = self._zhaoqing_start_date(region['name'])

        results = []
        for feed in region['feeds']:
            api_url = _ZHAOQING_API_URL.format(column_id=feed['column_id'])
            response = self.fetch(api_url, extra_headers={'Accept': 'application/json'})
            if response is None:
                logger.error('[eia] 肇庆 %s API 请求失败', feed['announcement_type'])
                return None
            try:
                payload = response.json()
            except ValueError:
                logger.error('[eia] 肇庆 %s API 返回非 JSON', feed['announcement_type'])
                return None

            if not isinstance(payload, dict) or 'articles' not in payload:
                logger.error('[eia] 肇庆 %s API schema 异常', feed['announcement_type'])
                return None

            articles = payload.get('articles', [])
            for article in articles:
                self._check_pause_and_stop()
                article_date = datetime.fromtimestamp(article['date']).date() if article.get('date') else None
                if start_date is not None and (article_date is None or article_date < start_date):
                    continue

                detail = self._fetch_zhaoqing_detail(article['url'])
                if detail is None:
                    logger.warning('[eia] 肍庆详情获取失败，保留列表核心字段: %s', article['url'])
                    results.append({
                        'project_name': article.get('title', ''),
                        'announcement_type': feed['announcement_type'],
                        'region': region['name'],
                        'publish_date': datetime.fromtimestamp(article['date']) if article.get('date') else None,
                        'source_url': article['url'],
                    })
                    continue

                item = self._zhaoqing_row_to_lead(article, detail, feed['announcement_type'], region['name'])
                results.append(item)

        mode = '全量' if start_date is None else f'{self.zhaoqing_lookback_days}天增量'
        logger.info('[eia] 肇庆(%s)采集到 %d 条结果', mode, len(results))
        return results

    def _fetch_zhaoqing_detail(self, url):
        """从详情页 HTML 提取内嵌的 window._CONFIG.DETAIL JSON。"""
        response = self.fetch(url)
        if response is None:
            return None
        html_text = response.text
        m = _ZHAOQING_DETAIL_RE.search(html_text)
        if not m:
            logger.error('[eia] 肍庆详情页未找到 DETAIL JSON: %s', url)
            return None
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error('[eia] 肍庆详情 DETAIL JSON 解析失败: %s - %s', url, exc)
            return None

    def _zhaoqing_row_to_lead(self, article, detail, announcement_type, region_name):
        """将肇庆 API 条目 + DETAIL JSON 表格映射为 lead 字段。"""
        # DETAIL.content 是 HTML table 字符串，用 _extract_kv_tables 解析
        content_html = detail.get('content', '')
        kv = {}
        if content_html:
            content_soup = BeautifulSoup(content_html, 'lxml')
            kv = self._extract_kv_tables(content_soup)

        publish_date = datetime.fromtimestamp(article['date']) if article.get('date') else None

        # 从表格提取核心字段
        project_name = kv.get('项目名称') or article.get('title', '')
        buyer_name = kv.get('建设单位', '')
        buyer_address = kv.get('建设地点', '')
        agency_name = kv.get('环评单位') or kv.get('环评机构', '')
        env_doc_type = kv.get('环评文件类型', '')

        # 提取联系电话（公告底部的"联系电话：0758-xxxxxxx"）
        full_text = content_soup.get_text('\n', strip=True) if content_soup else ''
        phone = self._extract_government_phone(full_text)

        # 提取附件链接
        source_files = []
        if content_soup:
            for a in content_soup.find_all('a', href=True):
                href = a['href']
                name = a.get_text(strip=True) or ''
                if _ATTACHMENT_EXT_RE.search(href) or _ATTACHMENT_EXT_RE.search(name):
                    source_files.append({'name': name, 'url': urljoin(_ZHAOQING_APP_URL, href)})

        result = {
            'project_name': project_name[:500],
            'buyer_name': buyer_name[:200],
            'buyer_address': buyer_address[:300],
            'agency_name': agency_name[:200],
            'announcement_type': announcement_type,
            'region': region_name,
            'publish_date': publish_date,
            'source_url': article['url'],
            'environment_document_type': env_doc_type,
            'source_files': source_files,
            '_raw_html': detail.get('content', ''),
        }
        if phone:
            result['phone'] = phone[:50]
            result['government_contact_role'] = '生态环境主管部门公众咨询电话'
        # 审批后公告可能有批复文号
        approval_number = kv.get('审批文号') or kv.get('批复文号')
        if approval_number:
            result['approval_number'] = approval_number
        return result

    # ------------------------------------------------------------------
    # POST 与 JSON 字段工具
    # ------------------------------------------------------------------
    def _post_response(self, url, *, json_body=None, form_data=None, accept='application/json'):
        if self.session is None:
            self._create_session()
        if self.check_robots and not self._check_robots(url):
            return None

        retries = max(1, self.max_retries)
        for attempt in range(1, retries + 1):
            try:
                time.sleep(self.get_random_delay())
                headers = {
                    'User-Agent': self.get_random_ua(),
                    'Accept': accept,
                }
                if json_body is not None:
                    headers['Content-Type'] = 'application/json'
                    response = self.session.post(url, json=json_body, headers=headers)
                else:
                    headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
                    response = self.session.post(url, data=form_data or {}, headers=headers)

                if 200 <= response.status_code < 300:
                    return response
                logger.warning('[eia] POST HTTP %d: %s', response.status_code, url)
                if response.status_code not in (429, 503):
                    return None
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
                logger.warning('[eia] POST 第 %d 次失败: %s - %s', attempt, url, exc)
            except Exception as exc:
                logger.error('[eia] POST 第 %d 次异常: %s - %s', attempt, url, exc)

            if attempt < retries:
                time.sleep(2 ** attempt)
        return None

    def _post_json(self, url, json_body):
        response = self._post_response(url, json_body=json_body)
        if response is None:
            return None
        try:
            payload = response.json()
        except ValueError:
            logger.error('[eia] POST JSON 接口返回非 JSON: %s - %s', url, response.text[:200])
            return None
        if not isinstance(payload, dict):
            logger.error('[eia] POST JSON 接口返回类型异常: %s', url)
            return None
        return payload

    def _post_form(self, url, form_data):
        # 该公开接口实测会拒绝 Accept: application/json（HTTP 403），官网请求
        # 使用宽泛 Accept；响应虽标 text/html，正文实际是 JSON。
        response = self._post_response(url, form_data=form_data, accept='*/*')
        if response is None:
            return None
        if '请输入验证码' in response.text:
            logger.error('[eia] 东莞列表触发验证码，分片已停止，未尝试绕过')
            return None
        try:
            payload = response.json()
        except ValueError:
            logger.error('[eia] 东莞列表返回非 JSON: %s', response.text[:200])
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
            logger.error('[eia] 东莞列表 schema 异常: %s', str(payload)[:300])
            return None
        for row in payload['rows']:
            if not isinstance(row, dict) or not str(row.get('ID') or '').strip():
                logger.error('[eia] 东莞列表存在无效记录: %s', str(row)[:200])
                return None
        try:
            payload['total'] = int(payload.get('total'))
        except (TypeError, ValueError):
            logger.error('[eia] 东莞列表 total 无效: %r', payload.get('total'))
            return None
        return payload

    @staticmethod
    def _parse_source_files(value, context):
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

    @staticmethod
    def _extract_government_phone(text):
        match = re.search(
            r'(?:联系电话|联系方式|电话)\s*[：:]\s*([0-9\-，,、\s]{5,40})',
            text or '',
        )
        if not match:
            return ''
        return re.split(r'传\s*真', match.group(1))[0].strip().rstrip('，,')

    @staticmethod
    def _parse_date(text):
        text = str(text or '').strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y年%m月%d日'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        # 佛山市日期格式为 MM-DD（无年份），自动补当前年份
        try:
            return datetime.strptime(f'{datetime.now().year}-{text}', '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _classify_category(title):
        if '受理' in title:
            return '受理公告'
        if '批复' in title:
            return '批复公告'
        if '批准决定' in title or '公示' in title:
            return '审批前公示'
        return '环评公示'

    @staticmethod
    def _extract_kv_tables(soup):
        """从详情页所有 <table> 提取结构化 key:value 字段（结构化优先于正则）。

        兼容两种表格形态：
        - 每行恰好2列：cells[0]为key，cells[1]为value。
        - 恰好2行且列数一致(>2列)：第1行为表头，第2行为数据，按列对齐 zip 成
          多组 key:value（如"受理日期|项目名称|建设单位|..."这种横向表格）。
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

    def _parse_detail(self, soup):
        kv = self._extract_kv_tables(soup)
        full_text = soup.get_text('\n', strip=True)

        project_name = kv.get('项目名称') or kv.get('批复名称') or ''
        buyer_name = kv.get('建设单位') or kv.get('行政相对人名称') or ''
        buyer_address = kv.get('建设地点', '')
        agency_name = (
            kv.get('环评机构')
            or kv.get('环评单位')
            or kv.get('环境影响评价机构')
            or ''
        )

        if not buyer_address:
            m = re.search(r'位于([^，。；\n]{4,50})', full_text)
            if m:
                buyer_address = m.group(1).strip()

        # 这里的电话是生态环境主管部门的公众咨询电话，不是建设单位的直接联系
        # 方式，见模块顶部说明。
        phone = self._extract_government_phone(full_text)

        result = {
            'project_name': project_name,
            'buyer_name': buyer_name,
            'buyer_address': buyer_address,
            'agency_name': agency_name,
            'phone': phone,
        }
        approval_number = kv.get('审批文号') or kv.get('批复文号')
        if approval_number:
            result['approval_number'] = approval_number
        approval_time = kv.get('审批时间') or kv.get('批复时间')
        if approval_time:
            result['approval_time'] = approval_time
        if phone:
            result['government_contact_role'] = '生态环境主管部门公众咨询电话'
        return result

    @staticmethod
    def _extract_attachments(soup, base_url):
        attachments = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if _ATTACHMENT_EXT_RE.search(href):
                url = urljoin(base_url, href)
                name = a.get_text(strip=True) or url.rsplit('/', 1)[-1]
                attachments.append({'url': url, 'name': name})
        return attachments
