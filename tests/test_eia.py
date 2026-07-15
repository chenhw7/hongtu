# -*- coding: utf-8 -*-
import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Attachment, Lead
from scraper.eia import EiaScraper, REGIONS
from scraper.eia.adapters.base import BaseAdapter
from scraper.eia.adapters.static import StaticAdapter
from scraper.eia.adapters.guangzhou import GuangzhouAdapter
from scraper.eia.adapters.dongguan import DongguanAdapter
from scraper.eia.adapters.zhaoqing import ZhaoqingAdapter


FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'eia'


def load_text(name):
    return (FIXTURE_DIR / name).read_text(encoding='utf-8')


def load_json(name):
    return json.loads(load_text(name))


class FakeResponse:
    def __init__(self, payload=None, text=None, status_code=200):
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload, ensure_ascii=False)
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError('not json')
        return self._payload


class EiaScraperTest(unittest.TestCase):
    def setUp(self):
        self.scraper = EiaScraper(app=None)
        self.scraper.delay_min = 0
        self.scraper.delay_max = 0
        # 预创建适配器用于直接测试
        self.gz = self.scraper._get_adapter(REGIONS['guangzhou'])
        self.dg = self.scraper._get_adapter(REGIONS['dongguan'])
        self.static = self.scraper._get_adapter(REGIONS['jiangmen'])

    # ------------------------------------------------------------------
    # 广州受理 API
    # ------------------------------------------------------------------
    def test_guangzhou_acceptance_maps_core_fields_without_downloading_files(self):
        payload = load_json('guangzhou_acceptance.json')
        self.scraper.fetch = Mock(return_value=FakeResponse(payload=payload))
        self.gz._fetch_detail = Mock()

        rows = self.gz._scrape_acceptance_page(1)

        self.assertEqual(len(rows), 1)
        lead = rows[0]
        self.assertEqual(lead['project_name'], '广州市测试建设项目')
        self.assertEqual(lead['buyer_name'], '广州测试建设有限公司')
        self.assertEqual(lead['publish_date'], date(2026, 7, 14))
        self.assertEqual(lead['announcement_type'], '受理公告')
        self.assertEqual(lead['phone'], '020-12345678')
        self.assertEqual(lead['source_files'][0]['name'], '测试项目公示稿.pdf')
        self.assertNotIn('attachments', lead)
        self.assertIn('#/hpslzs/index?id=SLGG-test-001', lead['source_url'])
        self.gz._fetch_detail.assert_not_called()

    def test_guangzhou_acceptance_rejects_short_or_duplicate_page(self):
        payload = load_json('guangzhou_acceptance.json')
        payload['data']['total'] = 2
        self.scraper.fetch = Mock(return_value=FakeResponse(payload=payload))
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.gz._scrape_acceptance_page(1))

    def test_guangzhou_acceptance_rejects_cross_page_drift_and_missing_core_fields(self):
        page_one = load_json('guangzhou_acceptance.json')
        page_one['data']['total'] = 101
        template = page_one['data']['list'][0]
        page_one['data']['list'] = [
            dict(template, ID=f'SLGG-test-{index:03d}') for index in range(100)
        ]
        page_two = {
            'code': 0,
            'data': {'total': 101, 'list': [dict(template, ID='SLGG-test-099')]},
        }
        self.scraper.fetch = Mock(side_effect=[
            FakeResponse(payload=page_one), FakeResponse(payload=page_two)
        ])

        self.assertEqual(len(self.gz._scrape_acceptance_page(1)), 100)
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.gz._scrape_acceptance_page(2))

        missing = load_json('guangzhou_acceptance.json')
        missing['data']['list'][0]['PROJECT_NAME'] = ''
        self.gz._total = None
        self.gz._seen_ids.clear()
        self.scraper.fetch = Mock(return_value=FakeResponse(payload=missing))
        self.gz._fetch_detail = Mock(return_value=None)
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.gz._scrape_acceptance_page(1))

    def test_guangzhou_acceptance_requires_all_core_fields_and_valid_date(self):
        invalid_cases = [
            ('CONSTRUCTION_UNIT', ''),
            ('CONSTRUCTION_LOCATION', '   '),
            ('ENV_ASSESSMENT_UNIT', None),
            ('PUBLISH_DATE', 'not-a-date'),
        ]
        for field, value in invalid_cases:
            with self.subTest(field=field):
                payload = load_json('guangzhou_acceptance.json')
                payload['data']['list'][0][field] = value
                if field == 'PUBLISH_DATE':
                    payload['data']['list'][0]['ACCEPTANCE_DATE'] = ''
                self.gz._total = None
                self.gz._seen_ids.clear()
                self.scraper.fetch = Mock(return_value=FakeResponse(payload=payload))
                self.gz._fetch_detail = Mock(return_value=None)
                with self.assertLogs('scraper.eia', level='ERROR'):
                    self.assertIsNone(self.gz._scrape_acceptance_page(1))

    def test_guangzhou_acceptance_rejects_total_change_between_pages(self):
        page_one = load_json('guangzhou_acceptance.json')
        page_one['data']['total'] = 101
        template = page_one['data']['list'][0]
        page_one['data']['list'] = [
            dict(template, ID=f'SLGG-test-{index:03d}') for index in range(100)
        ]
        page_two = {
            'code': 0,
            'data': {'total': 102, 'list': [dict(template, ID='SLGG-test-100')]},
        }
        self.scraper.fetch = Mock(side_effect=[
            FakeResponse(payload=page_one), FakeResponse(payload=page_two)
        ])
        self.assertEqual(len(self.gz._scrape_acceptance_page(1)), 100)
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.gz._scrape_acceptance_page(2))

        duplicate = load_json('guangzhou_acceptance.json')
        duplicate['data']['total'] = 2
        duplicate['data']['list'].append(dict(duplicate['data']['list'][0]))
        self.scraper.fetch = Mock(return_value=FakeResponse(payload=duplicate))
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.gz._scrape_acceptance_page(1))

    # ------------------------------------------------------------------
    # POST 响应
    # ------------------------------------------------------------------
    def test_post_response_accepts_created_status(self):
        self.scraper.session = Mock()
        self.scraper.session.post.return_value = FakeResponse(
            payload={'code': 0, 'data': {'ID': 'SLGG-test-001'}}, status_code=201
        )
        payload = self.gz._post_json(
            'http://example.invalid/detail', {'id': 'SLGG-test-001'}
        )
        self.assertEqual(payload['data']['ID'], 'SLGG-test-001')

    # ------------------------------------------------------------------
    # 广州静态 feed
    # ------------------------------------------------------------------
    def test_guangzhou_static_feed_uses_fixed_type_and_last_span_date(self):
        list_html = load_text('guangzhou_static_list.html')
        detail_html = load_text('guangzhou_static_detail.html')

        def fetch_html(url):
            html = list_html if url.endswith('index.html') else detail_html
            return html, BeautifulSoup(html, 'html.parser'), 200

        self.static.fetch_html_with_status = Mock(side_effect=fetch_html)
        feed = REGIONS['guangzhou']['feeds'][2]

        rows = self.static._scrape_single(
            feed, 1, region_name='广州市', announcement_type='批复公告'
        )

        self.assertEqual(len(rows), 1)
        lead = rows[0]
        self.assertEqual(lead['project_name'], '广州市测试建设项目')
        self.assertEqual(lead['publish_date'], date(2026, 7, 14))
        self.assertEqual(lead['announcement_type'], '批复公告')
        self.assertEqual(lead['approval_number'], '穗环管影〔2026〕1号')
        self.assertEqual(lead['phone'], '020-87654321')
        self.assertEqual(lead['attachments'][0]['name'], '批复文件.pdf')

    def test_original_static_adapter_still_parses_list_and_detail(self):
        list_html = (
            '<ul class="infoList"><li><a href="detail.html" title="测试项目受理公示">'
            '测试项目受理公示</a><span>2026-07-14</span></li></ul>'
        )
        detail_html = (
            '<table><tr><th>项目名称</th><td>测试项目</td></tr>'
            '<tr><th>建设单位</th><td>测试单位</td></tr></table>'
        )
        self.static.fetch_html_with_status = Mock(side_effect=[
            (list_html, BeautifulSoup(list_html, 'html.parser'), 200),
            (detail_html, BeautifulSoup(detail_html, 'html.parser'), 200),
        ])

        rows = self.static._scrape_single(REGIONS['jiangmen'], 1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['project_name'], '测试项目')
        self.assertEqual(rows[0]['buyer_name'], '测试单位')
        self.assertEqual(rows[0]['announcement_type'], '受理公告')

    def test_static_detail_404_keeps_list_core_fields(self):
        list_html = (
            '<ul class="infoList"><li><a href="missing.html" title="已下线项目受理公示">'
            '已下线项目受理公示</a><span>2026-07-14</span></li></ul>'
        )
        self.static.fetch_html_with_status = Mock(side_effect=[
            (list_html, BeautifulSoup(list_html, 'html.parser'), 200),
            (None, None, 404),
        ])

        with self.assertLogs('scraper.eia', level='WARNING'):
            rows = self.static._scrape_single(REGIONS['jiangmen'], 1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['project_name'], '已下线项目受理公示')
        self.assertEqual(rows[0]['publish_date'], date(2026, 7, 14))

    def test_static_404_ends_paging_but_source_failure_marks_task_failed(self):
        self.static.fetch_html_with_status = Mock(return_value=(None, None, 404))
        self.assertEqual(self.static._scrape_single(REGIONS['jiangmen'], 8), [])
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.static._scrape_single(REGIONS['jiangmen'], 1))

        # 模拟广州适配器采集失败 → _scrape_page 返回 None
        self.scraper._get_adapter = Mock()
        self.scraper._get_adapter.return_value.scrape_page = Mock(return_value=None)
        self.assertIsNone(self.scraper._scrape_page('region:guangzhou', 1))

    def test_source_failure_marks_base_task_failed(self):
        self.scraper.create_task = Mock(return_value=SimpleNamespace(id=123))
        self.scraper.update_task = Mock()
        self.scraper._create_session = Mock()
        self.scraper._close_session = Mock()
        self.scraper._progress_start = Mock()
        self.scraper._progress_update = Mock()
        self.scraper._progress_finish = Mock()
        self.scraper._progress_clear_control = Mock()

        # 模拟广州适配器失败、东莞适配器返回空
        self.scraper._get_adapter = Mock()
        mock_gz = Mock()
        mock_gz.scrape_page = Mock(return_value=None)
        mock_dg = Mock()
        mock_dg.scrape_page = Mock(return_value=[])
        self.scraper._get_adapter.side_effect = [mock_gz, mock_dg]

        with self.assertLogs(level='WARNING'):
            result = self.scraper.run(
                keywords=['region:guangzhou', 'region:dongguan'], max_pages=1
            )

        self.assertEqual(result, 0)
        mock_dg.scrape_page.assert_called_once()
        args, kwargs = self.scraper.update_task.call_args
        self.assertEqual(args[:2], (123, '失败'))
        self.assertEqual(kwargs['result_count'], 0)
        self.assertIn('广州市 第1页', kwargs['error_msg'])
        self.scraper._progress_finish.assert_called_once()
        self.assertEqual(self.scraper._progress_finish.call_args.args[0], '失败')

    # ------------------------------------------------------------------
    # 东莞
    # ------------------------------------------------------------------
    def test_dongguan_mapping_preserves_post_attachment_as_metadata(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        region = REGIONS['dongguan']
        feed = region['feeds'][0]

        lead = self.dg._row_to_lead(region, feed, row)

        self.assertEqual(lead['project_name'], '东莞市测试五金制品有限公司扩建项目')
        self.assertEqual(lead['buyer_name'], '东莞市测试五金制品有限公司')
        self.assertEqual(lead['publish_date'], date(2026, 7, 14))
        self.assertEqual(lead['acceptance_number'], '20260009730')
        self.assertEqual(lead['source_files'][0]['fileId'], 'file-test-1')
        self.assertNotIn('attachments', lead)
        self.assertNotIn('contact_person', lead)
        self.assertIn('id=dg-test-001', lead['source_url'])

    def test_dongguan_window_reads_public_detail_and_keeps_snapshot(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        detail_html = load_text('dongguan_detail.html')
        self.dg._fetch_feed = Mock(
            side_effect=lambda _region, feed, _start, _end: [row]
            if feed['announcement_type'] == '受理公告' else []
        )
        self.dg.fetch_html_with_status = Mock(
            return_value=(detail_html, BeautifulSoup(detail_html, 'html.parser'), 200)
        )

        rows = self.dg._scrape_window(
            REGIONS['dongguan'], date(2026, 7, 14), date(2026, 7, 14)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['agency_name'], '广东测试环保工程有限公司')
        self.assertEqual(rows[0]['_raw_html'], detail_html)
        self.assertEqual(self.dg.fetch_html_with_status.call_count, 1)

    def test_dongguan_window_supplements_approval_by_acceptance_number(self):
        region = REGIONS['dongguan']
        acceptance = load_json('dongguan_acceptance.json')['rows'][0]
        approval = {
            'HBTB_XH': acceptance['HBTB_XH'],
            'HBTB_XMMC': acceptance['HBTB_XMMC'],
            'HBTB_GSSJ': '2026-07-14 12:00:00',
            'HBTB_SPWH': '东环建〔2026〕1号',
            'ID': 'dg-approval-001',
        }

        def fetch_feed(_region, feed, _start, _end):
            if feed['announcement_type'] == '批复公告':
                return [approval]
            return []

        self.dg._fetch_feed = Mock(side_effect=fetch_feed)
        self.dg._fetch_acceptance_by_number = Mock(return_value=acceptance)
        self.dg.fetch_html_with_status = Mock(return_value=(None, None, 404))

        with self.assertLogs('scraper.eia', level='WARNING'):
            rows = self.dg._scrape_window(
                region, date(2026, 7, 14), date(2026, 7, 14)
            )

        approval_lead = next(row for row in rows if row['announcement_type'] == '批复公告')
        self.assertEqual(approval_lead['buyer_name'], acceptance['HBTB_JSDW'])
        self.assertEqual(approval_lead['buyer_address'], acceptance['HBTB_JSDD'])
        self.assertEqual(approval_lead['agency_name'], acceptance['HBTB_HPJG'])
        self.dg._fetch_acceptance_by_number.assert_called_once_with(
            region,
            str(acceptance['HBTB_XH']),
            acceptance['HBTB_XMMC'],
        )

    def test_dongguan_exact_acceptance_lookup_has_no_date_filter(self):
        region = REGIONS['dongguan']
        acceptance = load_json('dongguan_acceptance.json')['rows'][0]
        self.dg._post_form = Mock(return_value={'total': 1, 'rows': [acceptance]})

        row = self.dg._fetch_acceptance_by_number(
            region, str(acceptance['HBTB_XH']), acceptance['HBTB_XMMC']
        )

        self.assertEqual(row['ID'], acceptance['ID'])
        form = self.dg._post_form.call_args.args[1]
        self.assertEqual(form['HBTB_XH'], str(acceptance['HBTB_XH']))
        self.assertEqual(form['HBTB_XH_END'], str(acceptance['HBTB_XH']))
        self.assertEqual(form['HBTB_SLRQ'], '')
        self.assertEqual(form['HBTB_SLRQ_END'], '')

    def test_dongguan_detail_errors_fail_but_404_keeps_list_fields(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        region = REGIONS['dongguan']
        self.dg._fetch_feed = Mock(
            side_effect=lambda _region, feed, _start, _end: [row]
            if feed['announcement_type'] == '受理公告' else []
        )

        self.dg.fetch_html_with_status = Mock(return_value=(None, None, 403))
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.dg._scrape_window(
                region, date(2026, 7, 14), date(2026, 7, 14)
            ))

        self.dg.fetch_html_with_status = Mock(return_value=(None, None, 404))
        with self.assertLogs('scraper.eia', level='WARNING'):
            rows = self.dg._scrape_window(
                region, date(2026, 7, 14), date(2026, 7, 14)
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['project_name'], row['HBTB_XMMC'])

        broken_html = '<html><body>系统维护</body></html>'
        self.dg.fetch_html_with_status = Mock(return_value=(
            broken_html, BeautifulSoup(broken_html, 'html.parser'), 200
        ))
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.dg._scrape_window(
                region, date(2026, 7, 14), date(2026, 7, 14)
            ))

        wrong_detail = (
            '<table><tr><th>项目名称</th><td>另一个项目</td></tr>'
            '<tr><th>建设单位</th><td>错误单位</td></tr>'
            '<tr><th>建设地点</th><td>错误地点</td></tr></table>'
        )
        self.dg.fetch_html_with_status = Mock(return_value=(
            wrong_detail, BeautifulSoup(wrong_detail, 'html.parser'), 200
        ))
        with self.assertLogs('scraper.eia', level='ERROR'):
            self.assertIsNone(self.dg._scrape_window(
                region, date(2026, 7, 14), date(2026, 7, 14)
            ))

    def test_dongguan_splits_multi_day_result_before_page_four(self):
        region = REGIONS['dongguan']
        feed = region['feeds'][0]
        calls = []

        def request(_region, _feed, start_date, end_date, page, number_start=None, number_end=None):
            calls.append((start_date, end_date, page, number_start, number_end))
            if start_date != end_date:
                return {'total': 80, 'rows': [{'ID': f'probe-{i}', 'HBTB_XH': 20260000100 - i} for i in range(20)]}
            total = 40
            count = min(20, total - (page - 1) * 20)
            rows = [
                {'ID': f'{start_date}-{page}-{i}', 'HBTB_XH': 20260000100 - i}
                for i in range(count)
            ]
            return {'total': total, 'rows': rows}

        self.dg._request_page = Mock(side_effect=request)
        rows = self.dg._fetch_feed(
            region, feed, date(2026, 7, 13), date(2026, 7, 14)
        )

        self.assertEqual(len(rows), 80)
        self.assertTrue(all(call[2] <= 3 for call in calls))
        self.assertIn((date(2026, 7, 14), date(2026, 7, 14), 2, None, None), calls)
        self.assertIn((date(2026, 7, 13), date(2026, 7, 13), 2, None, None), calls)

    def test_dongguan_splits_single_day_by_acceptance_number(self):
        region = REGIONS['dongguan']
        feed = region['feeds'][0]
        calls = []

        def request(_region, _feed, start_date, end_date, page, number_start=None, number_end=None):
            calls.append((page, number_start, number_end))
            if number_start is None:
                return {
                    'total': 61,
                    'rows': [
                        {'ID': f'probe-{i}', 'HBTB_XH': 20260000100 - i}
                        for i in range(20)
                    ],
                }
            if (number_start, number_end) == (0, 100):
                return {
                    'total': 61,
                    'rows': [
                        {'ID': f'bounded-probe-{i}', 'HBTB_XH': 100 - i}
                        for i in range(20)
                    ],
                }
            total = 30 if number_start == 51 else 31
            count = min(20, total - (page - 1) * 20)
            rows = [
                {
                    'ID': f'{number_start}-{number_end}-{page}-{i}',
                    'HBTB_XH': number_end - (page - 1) * 20 - i,
                }
                for i in range(count)
            ]
            return {'total': total, 'rows': rows}

        self.dg._request_page = Mock(side_effect=request)
        with patch('scraper.eia.adapters.dongguan._DONGGUAN_NUMBER_MAX', 100):
            rows = self.dg._fetch_feed(
                region, feed, date(2026, 7, 14), date(2026, 7, 14)
            )

        self.assertEqual(len(rows), 61)
        self.assertTrue(all(page <= 3 for page, _, _ in calls))
        self.assertIn((1, 0, 100), calls)
        self.assertIn((1, 51, 100), calls)
        self.assertIn((1, 0, 50), calls)

    def test_dongguan_count_mismatch_fails_instead_of_returning_partial_rows(self):
        region = REGIONS['dongguan']
        feed = region['feeds'][0]

        def request(_region, _feed, _start, _end, page, number_start=None, number_end=None):
            if number_start is None:
                return {
                    'total': 61,
                    'rows': [{'ID': f'unbounded-{i}', 'HBTB_XH': i} for i in range(20)],
                }
            # 模拟空/非数字受理号不在数字筛选域中：数字域总量比父分片少 1。
            total = 60
            count = min(20, total - (page - 1) * 20)
            return {
                'total': total,
                'rows': [
                    {'ID': f'bounded-{page}-{i}', 'HBTB_XH': i}
                    for i in range(count)
                ],
            }

        self.dg._request_page = Mock(side_effect=request)
        with patch('scraper.eia.adapters.dongguan._DONGGUAN_NUMBER_MAX', 100):
            with self.assertLogs('scraper.eia', level='ERROR'):
                rows = self.dg._fetch_feed(
                    region, feed, date(2026, 7, 14), date(2026, 7, 14)
                )
        self.assertIsNone(rows)

    def test_dongguan_rejects_page_four_and_captcha_response(self):
        region = REGIONS['dongguan']
        feed = region['feeds'][0]
        with self.assertRaises(ValueError):
            self.dg._request_page(
                region, feed, date(2026, 7, 14), date(2026, 7, 14), 4
            )

        response = FakeResponse(text="<script>alert('请输入验证码');</script>")
        self.dg._post_response = Mock(return_value=response)
        with self.assertLogs('scraper.eia', level='ERROR'):
            payload = self.dg._post_form('https://example.invalid/item.do', {})
        self.assertIsNone(payload)

        self.dg._post_response = Mock(return_value=FakeResponse(payload={
            'total': 1,
            'rows': [{'HBTB_XH': 20260000001, 'HBTB_XMMC': '无ID项目'}],
        }))
        with self.assertLogs('scraper.eia', level='ERROR'):
            payload = self.dg._post_form('https://example.invalid/item.do', {})
        self.assertIsNone(payload)


class ZhaoqingScraperTest(unittest.TestCase):
    """肇庆 gkmlpt JSON API 适配器测试"""

    def setUp(self):
        self.scraper = EiaScraper(app=None)
        self.scraper.delay_min = 0
        self.scraper.delay_max = 0
        self.zq = self.scraper._get_adapter(REGIONS['zhaoqing'])

    def test_zhaoqing_api_list_maps_core_fields(self):
        """列表 API + 详情页 → lead 字段完整映射（仅测试受理公告 feed）"""
        api_data = load_json('zhaoqing_acceptance.json')
        detail_html = load_text('zhaoqing_detail.html')

        region = REGIONS['zhaoqing']
        single_feed = [region['feeds'][0]]

        detail_response = FakeResponse(text=detail_html)
        self.scraper.fetch = Mock(side_effect=[
            FakeResponse(payload=api_data),
            detail_response,
            detail_response,
        ])
        with patch.dict(REGIONS, {'zhaoqing': dict(region, feeds=single_feed)}):
            with patch.object(self.zq, '_resolve_start_date', return_value=None):
                results = self.zq.scrape_page(REGIONS['zhaoqing'], 1)

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)

    def test_zhaoqing_row_to_lead_maps_kv_fields(self):
        """DETAIL JSON 表格 KV 映射到 lead 字段"""
        api_data = load_json('zhaoqing_acceptance.json')
        article = api_data['articles'][0]

        detail_html = load_text('zhaoqing_detail.html')
        m = __import__('re').search(r'DETAIL:\s*({.*?})\s*,\s*TREE:', detail_html)
        detail = json.loads(m.group(1))

        lead = self.zq._row_to_lead(
            article, detail, '受理公告', '肇庆市'
        )

        self.assertEqual(lead['project_name'], '金宸农牧科技（四会）有限公司四会富硒蛋鸡产业园项目')
        self.assertEqual(lead['buyer_name'], '金宸农牧科技（四会）有限公司')
        self.assertEqual(lead['buyer_address'], '肇庆市四会市')
        self.assertEqual(lead['agency_name'], '广东清芯环保科技有限公司')
        self.assertEqual(lead['announcement_type'], '受理公告')
        self.assertEqual(lead['region'], '肇庆市')
        self.assertEqual(lead['environment_document_type'], '环境影响报告书')
        self.assertEqual(lead['phone'], '0758-2781002')
        self.assertEqual(lead['government_contact_role'], '生态环境主管部门公众咨询电话')
        self.assertEqual(lead['source_url'], article['url'])
        self.assertEqual(len(lead['source_files']), 1)
        self.assertIn('3255421.pdf', lead['source_files'][0]['url'])

    def test_zhaoqing_page_greater_than_one_returns_empty(self):
        """page > 1 立即返回空列表（API 单页全量模式）"""
        region = REGIONS['zhaoqing']
        result = self.zq.scrape_page(region, 2)
        self.assertEqual(result, [])

    def test_zhaoqing_api_failure_returns_none(self):
        """列表 API 请求失败 → None"""
        self.scraper.fetch = Mock(return_value=None)
        region = REGIONS['zhaoqing']
        result = self.zq.scrape_page(region, 1)
        self.assertIsNone(result)

    def test_zhaoqing_api_non_json_returns_none(self):
        """列表 API 返回非 JSON → None"""
        self.scraper.fetch = Mock(return_value=FakeResponse(text='<html>not json</html>'))
        region = REGIONS['zhaoqing']
        with self.assertLogs('scraper.eia', level='ERROR'):
            result = self.zq.scrape_page(region, 1)
        self.assertIsNone(result)

    def test_zhaoqing_detail_failure_preserves_list_fields(self):
        """详情获取失败 → 保留列表核心字段（标题、类型、日期）"""
        api_data = load_json('zhaoqing_acceptance.json')

        region = REGIONS['zhaoqing']
        single_feed = [region['feeds'][0]]

        self.scraper.fetch = Mock(side_effect=[
            FakeResponse(payload=api_data),
            None,
            None,
        ])
        with patch.dict(REGIONS, {'zhaoqing': dict(region, feeds=single_feed)}):
            with patch.object(self.zq, '_resolve_start_date', return_value=None):
                with self.assertLogs('scraper.eia', level='WARNING'):
                    results = self.zq.scrape_page(REGIONS['zhaoqing'], 1)
        self.assertIsNotNone(results)
        self.assertGreaterEqual(len(results), 1)
        lead = results[0]
        self.assertIn('project_name', lead)
        self.assertEqual(lead['announcement_type'], '受理公告')

    def test_zhaoqing_start_date_returns_none_below_threshold(self):
        """DB 中肇庆 lead < 阈值 → 全量模式（start_date=None）"""
        mock_app = Mock()
        mock_app.config = {}
        scraper = EiaScraper(app=mock_app)
        scraper.zhaoqing_lookback_days = 3
        zq = scraper._get_adapter(REGIONS['zhaoqing'])

        mock_ctx = Mock()
        mock_app.app_context.return_value = mock_ctx
        mock_ctx.__enter__ = Mock(return_value=None)
        mock_ctx.__exit__ = Mock(return_value=False)
        with patch('app.models.Lead') as mock_lead:
            mock_lead.query.filter.return_value.count.return_value = 2
            start_date = zq._resolve_start_date('肇庆市')
        self.assertIsNone(start_date)

    def test_zhaoqing_start_date_returns_window_above_threshold(self):
        """DB 中肇庆 lead ≥ 阈值 → 增量模式（start_date 为3天前）"""
        mock_app = Mock()
        mock_app.config = {}
        scraper = EiaScraper(app=mock_app)
        scraper.zhaoqing_lookback_days = 3
        zq = scraper._get_adapter(REGIONS['zhaoqing'])

        mock_ctx = Mock()
        mock_app.app_context.return_value = mock_ctx
        mock_ctx.__enter__ = Mock(return_value=None)
        mock_ctx.__exit__ = Mock(return_value=False)
        with patch('app.models.Lead') as mock_lead:
            mock_lead.query.filter.return_value.count.return_value = 80
            start_date = zq._resolve_start_date('肇庆市')
        self.assertIsNotNone(start_date)
        expected = datetime.now().date() - timedelta(days=3)
        self.assertEqual(start_date, expected)


class EiaDatabaseTest(unittest.TestCase):
    """数据库写入相关测试（需要 Flask 应用上下文）"""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite://',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SCRAPE_SAVE_SNAPSHOT=False,
            SCRAPE_DOWNLOAD_ATTACHMENTS=True,
            EIA_DELAY_MIN=0,
            EIA_DELAY_MAX=0,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.scraper = EiaScraper(app=self.app)
        self.scraper._save_attachments = Mock()
        self.dg = self.scraper._get_adapter(REGIONS['dongguan'])

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def test_save_keeps_restricted_files_in_raw_data_and_project_level_dedup(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        region = REGIONS['dongguan']
        acceptance = self.dg._row_to_lead(region, region['feeds'][0], row)

        count = self.scraper.save_leads([acceptance], 'eia')

        self.assertEqual(count, 1)
        saved = Lead.query.one()
        raw_data = json.loads(saved.raw_data)
        self.assertEqual(raw_data['source_files'][0]['fileId'], 'file-test-1')
        self.assertEqual(Attachment.query.count(), 0)
        self.scraper._save_attachments.assert_not_called()

        later_stage = dict(acceptance, announcement_type='审批前公示')
        self.assertEqual(self.scraper.save_leads([later_stage], 'eia'), 0)
        self.assertEqual(Lead.query.count(), 1)

    def test_database_write_failure_is_not_reported_as_duplicate(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        lead = self.dg._row_to_lead(
            REGIONS['dongguan'], REGIONS['dongguan']['feeds'][0], row
        )

        with patch.object(db.session, 'commit', side_effect=RuntimeError('disk full')):
            with self.assertLogs('scraper.base', level='ERROR'):
                with self.assertRaisesRegex(RuntimeError, 'disk full'):
                    self.scraper.save_leads([lead], 'eia')

        self.assertEqual(Lead.query.count(), 0)

    def test_non_unique_integrity_error_is_not_reported_as_duplicate(self):
        row = load_json('dongguan_acceptance.json')['rows'][0]
        lead = self.dg._row_to_lead(
            REGIONS['dongguan'], REGIONS['dongguan']['feeds'][0], row
        )
        error = IntegrityError(
            'INSERT INTO leads', {}, Exception('NOT NULL constraint failed: leads.project_name')
        )

        with patch.object(db.session, 'commit', side_effect=error):
            with self.assertLogs('scraper.base', level='ERROR'):
                with self.assertRaises(IntegrityError):
                    self.scraper.save_leads([lead], 'eia')

        self.assertEqual(Lead.query.count(), 0)


if __name__ == '__main__':
    unittest.main()