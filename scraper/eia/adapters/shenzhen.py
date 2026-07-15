# -*- coding: utf-8 -*-
"""深圳环评公示适配器。

列表为服务端渲染的 .vm 页（ep.meeb.sz.gov.cn:8443），详情为静态 htmltemp 页，
均为公开 GET，无登录/Cookie/签名。
"""
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.eia import utils
from scraper.eia.regions import (
    _SHENZHEN_BASE,
    _SHENZHEN_DETAIL_URL,
    _SHENZHEN_DOREAD_RE,
    _SHENZHEN_LIST_URL,
    _SHENZHEN_PAGE_SIZE,
)
from scraper.eia.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class ShenzhenAdapter(BaseAdapter):
    """深圳环评采集适配器：服务端渲染 .vm 列表 + 静态 htmltemp 详情。"""

    def scrape_page(self, region, page):
        results = []
        for feed in region['feeds']:
            rows = self._scrape_feed_page(feed, page)
            if rows is None:
                return None
            results.extend(rows)
        return results

    def _scrape_feed_page(self, feed, page):
        gstype = feed['gstype']
        list_url = _SHENZHEN_LIST_URL.format(gstype=gstype)
        response = self.scraper.fetch(
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

        total_pages = self._total_pages(soup)
        if total_pages is not None and page > total_pages:
            return []

        nodes = [
            node for node in soup.select('div.form-group')
            if node.find('a', attrs={'onclick': _SHENZHEN_DOREAD_RE})
        ]
        results = []
        for node in nodes:
            self.scraper._check_pause_and_stop()
            a = node.find('a', attrs={'onclick': _SHENZHEN_DOREAD_RE})
            match = _SHENZHEN_DOREAD_RE.search(a.get('onclick') or '')
            if not match:
                continue
            pkid, gs = match.group(1), match.group(2)
            title = a.get_text(strip=True)
            date_node = node.select_one('p.form-control-static') or node.select_one('.col-sm-2')
            publish_date = utils.parse_date(date_node.get_text(strip=True) if date_node else '')
            detail_url = _SHENZHEN_DETAIL_URL.format(pkid=pkid, gstype=gs)

            lead = {
                'project_name': title,
                'announcement_type': feed['announcement_type'],
                'region': '深圳市',
                'publish_date': publish_date,
                'source_url': detail_url,
                'source_record_id': pkid,
            }
            detail_html, detail_soup, detail_status = self.fetch_html_with_status(detail_url)
            if detail_status == 404:
                logger.warning('[eia] 深圳详情已下线，保留列表核心字段: %s', detail_url)
            elif detail_soup is None:
                logger.error('[eia] 深圳详情请求失败: %s', detail_url)
                return None
            else:
                detail = {
                    key: value for key, value in self._parse_detail(detail_soup).items()
                    if value not in (None, '')
                }
                lead.update(detail)
                lead['_raw_html'] = detail_html
            results.append(lead)

        logger.info('[eia] 深圳 gstype=%s 第 %d 页解析到 %d 条结果', gstype, page, len(results))
        return results

    @staticmethod
    def _total_pages(soup):
        el = soup.find('input', attrs={'name': 'pages'})
        if el is not None and str(el.get('value') or '').isdigit():
            return int(el['value'])
        return None

    def _parse_detail(self, soup):
        """深圳详情页表格是「2 格行 + 4 格行」混排，按\"标签以：结尾→取下一格为值\"成对解析。"""
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
        phone = utils.extract_government_phone(full_text)

        source_files = []
        for a in soup.find_all('a', href=True):
            name = a.get_text(strip=True)
            if name and utils.ATTACHMENT_EXT_RE.search(name):
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