# -*- coding: utf-8 -*-
"""广州环评公示适配器。

受理公告通过公开 JSON API 获取列表，必要时 POST 详情补全字段；
审批前公示和批复公告通过静态 HTML 解析。
"""
import logging
from urllib.parse import quote, urlencode

from scraper.eia import utils
from scraper.eia.regions import (
    REGIONS,
    _GUANGZHOU_DETAIL_PAGE,
    _GUANGZHOU_DETAIL_URL,
    _GUANGZHOU_LIST_URL,
    _GUANGZHOU_PAGE_SIZE,
)
from scraper.eia.adapters.base import BaseAdapter
from scraper.eia.adapters.static import StaticAdapter

logger = logging.getLogger(__name__)


class GuangzhouAdapter(BaseAdapter):
    """广州环评采集适配器：受理 JSON API + 两个静态 HTML feed。"""

    def __init__(self, scraper):
        super().__init__(scraper)
        self._static = StaticAdapter(scraper)
        self._total = None
        self._seen_ids = set()

    def scrape_page(self, region, page):
        if page == 1:
            self._total = None
            self._seen_ids.clear()
        results = []
        for feed in region['feeds']:
            if feed['type'] == 'gz_acceptance_api':
                rows = self._scrape_acceptance_page(page)
            else:
                rows = self._static._scrape_single(
                    feed,
                    page,
                    region_name=region['name'],
                    announcement_type=feed['announcement_type'],
                )
            if rows is None:
                return None
            results.extend(rows)
        return results

    # ------------------------------------------------------------------
    # 受理公告 JSON API
    # ------------------------------------------------------------------
    def _scrape_acceptance_page(self, page):
        params = {
            'PROJECT_NAME': '',
            'CONSTRUCTION_UNIT': '',
            'pageNum': page,
            'pageSize': _GUANGZHOU_PAGE_SIZE,
        }
        response = self.scraper.fetch(
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
        if self._total is None:
            self._total = total
        elif total != self._total:
            logger.error('[eia] 广州受理抓取期间 total 变化: %d -> %d', self._total, total)
            return None
        if (page - 1) * _GUANGZHOU_PAGE_SIZE >= total:
            return []

        expected_count = min(_GUANGZHOU_PAGE_SIZE, total - (page - 1) * _GUANGZHOU_PAGE_SIZE)
        if len(rows) != expected_count:
            logger.error(
                '[eia] 广州受理第 %d 页数量不守恒，期望 %d 条，实际 %d 条',
                page, expected_count, len(rows),
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
        repeated_ids = self._seen_ids.intersection(record_ids)
        if repeated_ids:
            logger.error('[eia] 广州受理跨页出现重复 ID: %s', sorted(repeated_ids)[:5])
            return None

        results = []
        for row in rows:
            self.scraper._check_pause_and_stop()
            merged = dict(row)
            record_id = merged.get('ID')
            if record_id and (
                not merged.get('PROJECT_NAME')
                or not merged.get('CONSTRUCTION_UNIT')
                or not merged.get('CONSTRUCTION_LOCATION')
                or not merged.get('ENV_ASSESSMENT_UNIT')
                or not (merged.get('PUBLISH_DATE') or merged.get('ACCEPTANCE_DATE'))
                or merged.get('FILELIST') is None
            ):
                detail = self._fetch_detail(record_id)
                if detail:
                    merged.update({k: v for k, v in detail.items() if v not in (None, '')})
            required_fields = (
                'PROJECT_NAME', 'CONSTRUCTION_UNIT',
                'CONSTRUCTION_LOCATION', 'ENV_ASSESSMENT_UNIT',
            )
            publish_value = merged.get('PUBLISH_DATE') or merged.get('ACCEPTANCE_DATE')
            if any(not str(merged.get(field) or '').strip() for field in required_fields) or (
                utils.parse_date(publish_value) is None
            ):
                logger.error('[eia] 广州受理核心字段补全失败，ID=%s', record_id)
                return None
            results.append(self._row_to_lead(merged))

        self._seen_ids.update(record_ids)
        logger.info('[eia] 广州受理第 %d 页解析到 %d 条结果', page, len(results))
        return results

    def _fetch_detail(self, record_id):
        payload = self._post_json(_GUANGZHOU_DETAIL_URL, {'id': str(record_id)})
        if payload is None:
            return None
        data = payload.get('data') if isinstance(payload, dict) else None
        if payload.get('code') not in (0, '0') or not isinstance(data, dict):
            logger.warning('[eia] 广州受理详情 schema 异常，ID=%s', record_id)
            return None
        return data

    def _row_to_lead(self, row):
        record_id = str(row.get('ID') or '').strip()
        remark = str(row.get('REMARK') or '').strip()
        phone = utils.extract_government_phone(remark)
        source_files = utils.parse_source_files(row.get('FILELIST'), f'广州 ID={record_id}')
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
            'publish_date': utils.parse_date(row.get('PUBLISH_DATE') or row.get('ACCEPTANCE_DATE')),
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