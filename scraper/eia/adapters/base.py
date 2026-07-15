# -*- coding: utf-8 -*-
"""环评公示适配器基类。

提供所有适配器共用的 HTTP 辅助方法和详情页解析逻辑。
"""
import logging
import re
import time

import httpx
from bs4 import BeautifulSoup

from scraper.eia import utils

logger = logging.getLogger(__name__)


class BaseAdapter:
    """环评采集适配器基类。

    子类需实现 scrape_page(region, page) -> list[dict] | None。
    """

    def __init__(self, scraper):
        """scraper 为 EiaScraper 实例，用于访问 fetch()、session 等资源。"""
        self.scraper = scraper

    # ------------------------------------------------------------------
    # 抽象接口
    # ------------------------------------------------------------------
    def scrape_page(self, region, page):
        """采集一个逻辑页，返回 lead 列表或 None（出错）或 []（无更多数据）。"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # HTTP 辅助
    # ------------------------------------------------------------------
    def fetch_html_with_status(self, url):
        """返回 (html_text, soup, status_code)；网络错误返回 (None, None, None)。"""
        response = self.scraper.fetch(url, return_error_response=True)
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

    def _post_response(self, url, *, json_body=None, form_data=None, accept='application/json'):
        """通用 POST 请求，带重试和 User-Agent 轮换。"""
        if self.scraper.session is None:
            self.scraper._create_session()
        if self.scraper.check_robots and not self.scraper._check_robots(url):
            return None

        retries = max(1, self.scraper.max_retries)
        for attempt in range(1, retries + 1):
            try:
                time.sleep(self.scraper.get_random_delay())
                headers = {
                    'User-Agent': self.scraper.get_random_ua(),
                    'Accept': accept,
                }
                if json_body is not None:
                    headers['Content-Type'] = 'application/json'
                    response = self.scraper.session.post(url, json=json_body, headers=headers)
                else:
                    headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
                    response = self.scraper.session.post(url, data=form_data or {}, headers=headers)

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
        """POST JSON 接口，返回解析后的 dict 或 None。"""
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
        """POST 表单接口（东莞专用），返回解析后的 dict 或 None。"""
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

    # ------------------------------------------------------------------
    # 详情页解析
    # ------------------------------------------------------------------
    def parse_detail(self, soup):
        """从详情页 HTML 提取结构化字段（通用逻辑，适用于静态 HTML 和东莞）。"""
        kv = utils.extract_kv_tables(soup)
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

        phone = utils.extract_government_phone(full_text)

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