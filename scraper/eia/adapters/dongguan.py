# -*- coding: utf-8 -*-
"""东莞环评公示适配器。

通过官网 iframe 使用的公开表单接口 POST 获取列表，再 GET 公开详情页。
第 4 页起要求验证码，因此只使用官网日期/受理号筛选，把每个结果分片限制在前三页以内。
"""
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from scraper.eia import utils
from scraper.eia.regions import (
    _DONGGUAN_DETAIL_URL,
    _DONGGUAN_LIST_URL,
    _DONGGUAN_MAX_PAGES_WITHOUT_CAPTCHA,
    _DONGGUAN_MAX_RESULTS_PER_SLICE,
    _DONGGUAN_MAX_SPLIT_DEPTH,
    _DONGGUAN_NUMBER_MAX,
    _DONGGUAN_NUMBER_MIN,
    _DONGGUAN_PAGE_SIZE,
)
from scraper.eia.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class DongguanAdapter(BaseAdapter):
    """东莞环评采集适配器：公开 POST 列表 + GET 详情。"""

    def __init__(self, scraper):
        super().__init__(scraper)
        self.lookback_days = getattr(scraper, 'dongguan_lookback_days', 2)

    def scrape_page(self, region, page):
        """BaseScraper 仍按逻辑页循环；东莞在第一页内部完成日期/受理号分片，
        后续逻辑页立即结束，绝不把 page=4 传给网站。"""
        if page > 1:
            return []
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=self.lookback_days - 1)
        return self._scrape_window(region, start_date, end_date)

    # ------------------------------------------------------------------
    # 窗口采集主流程
    # ------------------------------------------------------------------
    def _scrape_window(self, region, start_date, end_date):
        raw_records = []
        seen = set()
        for feed in region['feeds']:
            rows = self._fetch_feed(region, feed, start_date, end_date)
            if rows is None:
                return None
            for row in rows:
                record_key = (feed['dir_id'], str(row['ID']).strip())
                if record_key in seen:
                    continue
                seen.add(record_key)
                raw_records.append((feed, row))

        # 通过受理号关联，补全非受理公告的建设单位等字段
        related_by_number = {}
        for _, row in raw_records:
            acceptance_number = str(row.get('HBTB_XH') or '').strip()
            if acceptance_number and row.get('HBTB_JSDW'):
                related_by_number[acceptance_number] = row
        related_lookup_cache = {}

        leads = []
        for feed, row in raw_records:
            self.scraper._check_pause_and_stop()
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
                    related_lookup_cache[acceptance_number] = self._fetch_acceptance_by_number(
                        region, acceptance_number, merged_row.get('HBTB_XMMC'),
                    )
                related = related_lookup_cache[acceptance_number]
                if related is None:
                    return None
            if related is not None:
                for field in ('HBTB_JSDW', 'HBTB_JSDD', 'HBTB_HPJG'):
                    if not merged_row.get(field) and related.get(field):
                        merged_row[field] = related[field]

            lead = self._row_to_lead(region, feed, merged_row)
            detail_html, detail_soup, detail_status = self.fetch_html_with_status(lead['source_url'])
            if detail_status == 404:
                logger.warning('[eia] 东莞详情已下线，保留列表核心字段: %s', lead['source_url'])
            elif detail_soup is None:
                logger.error('[eia] 东莞详情请求失败: %s', lead['source_url'])
                return None
            elif not self._validate_detail(detail_soup, feed, merged_row):
                logger.error('[eia] 东莞详情模板或记录身份异常: %s', lead['source_url'])
                return None
            else:
                detail = {
                    key: value for key, value in self.parse_detail(detail_soup).items()
                    if value not in (None, '')
                }
                lead.update(detail)
                lead['_raw_html'] = detail_html
            leads.append(lead)

        logger.info('[eia] 东莞 %s 至 %s 共解析到 %d 条结果', start_date, end_date, len(leads))
        return leads

    # ------------------------------------------------------------------
    # 列表获取（含日期/受理号分片递归）
    # ------------------------------------------------------------------
    def _fetch_feed(self, region, feed, start_date, end_date,
                    number_start=None, number_end=None, depth=0):
        if depth > _DONGGUAN_MAX_SPLIT_DEPTH:
            logger.error('[eia] 东莞分片递归超过安全深度: %s 至 %s', start_date, end_date)
            return None

        first = self._request_page(region, feed, start_date, end_date, 1, number_start, number_end)
        if first is None:
            return None
        total = first['total']

        if total <= _DONGGUAN_MAX_RESULTS_PER_SLICE:
            rows = list(first['rows'])
            page_count = (total + _DONGGUAN_PAGE_SIZE - 1) // _DONGGUAN_PAGE_SIZE
            for p in range(2, page_count + 1):
                payload = self._request_page(region, feed, start_date, end_date, p, number_start, number_end)
                if payload is None:
                    return None
                if payload['total'] != total:
                    logger.error('[eia] 东莞分片抓取期间 total 变化: %d -> %d', total, payload['total'])
                    return None
                rows.extend(payload['rows'])
            rows = _deduplicate_rows(rows)
            if len(rows) != total:
                logger.error('[eia] 东莞分片数量不守恒，期望 %d 条，实际唯一记录 %d 条', total, len(rows))
                return None
            return rows

        if start_date < end_date and number_start is None and number_end is None:
            midpoint = start_date + timedelta(days=(end_date - start_date).days // 2)
            newer = self._fetch_feed(region, feed, midpoint + timedelta(days=1), end_date, depth=depth + 1)
            if newer is None:
                return None
            older = self._fetch_feed(region, feed, start_date, midpoint, depth=depth + 1)
            if older is None:
                return None
            merged = _deduplicate_rows(newer + older)
            if len(merged) != total:
                logger.error('[eia] 东莞日期分片数量不守恒，期望 %d 条，实际 %d 条', total, len(merged))
                return None
            return merged

        if number_start is None or number_end is None:
            bounded = self._fetch_feed(
                region, feed, start_date, end_date,
                _DONGGUAN_NUMBER_MIN, _DONGGUAN_NUMBER_MAX, depth + 1,
            )
            if bounded is None:
                return None
            if len(bounded) != total:
                logger.error(
                    '[eia] 东莞受理号全域未覆盖全部记录，未筛选 %d 条，数字域内 %d 条',
                    total, len(bounded),
                )
                return None
            return bounded

        try:
            low, high = int(number_start), int(number_end)
        except (TypeError, ValueError):
            logger.error('[eia] 东莞受理号范围无效: %r-%r', number_start, number_end)
            return None
        if low >= high:
            logger.error(
                '[eia] 东莞同一受理号范围仍超过 %d 条，无法合规继续拆分: %s-%s',
                _DONGGUAN_MAX_RESULTS_PER_SLICE, low, high,
            )
            return None

        midpoint = (low + high) // 2
        newer = self._fetch_feed(region, feed, start_date, end_date, midpoint + 1, high, depth + 1)
        if newer is None:
            return None
        older = self._fetch_feed(region, feed, start_date, end_date, low, midpoint, depth + 1)
        if older is None:
            return None
        merged = _deduplicate_rows(newer + older)
        if len(merged) != total:
            logger.error('[eia] 东莞受理号分片数量不守恒，期望 %d 条，实际 %d 条', total, len(merged))
            return None
        return merged

    def _request_page(self, region, feed, start_date, end_date, page, number_start=None, number_end=None):
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

    # ------------------------------------------------------------------
    # 受理号补全
    # ------------------------------------------------------------------
    def _fetch_acceptance_by_number(self, region, acceptance_number, project_name):
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
                acceptance_number, payload['total'], len(payload['rows']),
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

    # ------------------------------------------------------------------
    # 详情校验与行映射
    # ------------------------------------------------------------------
    def _validate_detail(self, soup, feed, row):
        kv = utils.extract_kv_tables(soup)
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

    def _row_to_lead(self, region, feed, row):
        record_id = str(row.get('ID') or '').strip()
        source_url = _DONGGUAN_DETAIL_URL + '?' + urlencode({
            'dirId': feed['dir_id'],
            'id': record_id,
            'subjectId': region['subject_id'],
        })
        source_files = utils.parse_source_files(
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
            'publish_date': utils.parse_date(publish_value),
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
# 模块级工具
# ------------------------------------------------------------------
def _deduplicate_rows(rows):
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