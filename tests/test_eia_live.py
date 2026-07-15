# -*- coding: utf-8 -*-
import os
import unittest
from datetime import datetime
from urllib.parse import urljoin

from scraper.eia import EiaScraper, REGIONS


@unittest.skipUnless(os.environ.get('EIA_LIVE_TESTS') == '1', '设置 EIA_LIVE_TESTS=1 才运行官网烟雾测试')
class EiaLiveSmokeTest(unittest.TestCase):
    def setUp(self):
        self.scraper = EiaScraper(app=None)
        self.scraper.delay_min = 0
        self.scraper.delay_max = 0
        self.gz = self.scraper._get_adapter(REGIONS['guangzhou'])
        self.dg = self.scraper._get_adapter(REGIONS['dongguan'])

    def tearDown(self):
        self.scraper._close_session()

    def test_guangzhou_public_acceptance_api(self):
        rows = self.gz._scrape_acceptance_page(1)
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        self.assertTrue(rows[0]['project_name'])
        self.assertEqual(rows[0]['region'], '广州市')
        record_id = rows[0]['source_record_id']
        detail = self.gz._fetch_detail(record_id)
        self.assertIsInstance(detail, dict)
        self.assertEqual(str(detail.get('ID')), record_id)

    def test_guangzhou_static_feeds(self):
        static = self.scraper._get_adapter(REGIONS['jiangmen'])  # StaticAdapter
        for feed in REGIONS['guangzhou']['feeds']:
            if feed['type'] != 'static':
                continue
            _, list_soup, status = static.fetch_html_with_status(feed['list_url'])
            self.assertEqual(status, 200)
            items = list_soup.select(feed['list_selector'])
            self.assertGreater(len(items), 0)
            link = items[0].find('a', href=True)
            self.assertIsNotNone(link)
            detail_url = urljoin(feed['list_url'], link['href'])
            _, detail_soup, detail_status = static.fetch_html_with_status(detail_url)
            self.assertEqual(detail_status, 200)
            self.assertGreater(len(detail_soup.find_all('table')), 0)

    def test_dongguan_public_form_api(self):
        region = REGIONS['dongguan']
        today = datetime.now().date()
        detail_checked = 0
        for feed in region['feeds']:
            payload = self.dg._request_page(region, feed, today, today, 1)
            bounded = self.dg._request_page(
                region, feed, today, today, 1, 0, 99_999_999_999
            )
            self.assertIsInstance(payload, dict)
            self.assertIsInstance(payload['total'], int)
            self.assertIsInstance(payload['rows'], list)
            self.assertEqual(bounded['total'], payload['total'])
            if feed['announcement_type'] != '受理公告' and payload['rows']:
                source_row = payload['rows'][0]
                acceptance_number = str(source_row.get('HBTB_XH') or '')
                if acceptance_number:
                    related = self.dg._fetch_acceptance_by_number(
                        region, acceptance_number, source_row.get('HBTB_XMMC')
                    )
                    self.assertIsInstance(related, dict)
                    if related:
                        self.assertEqual(str(related.get('HBTB_XH')), acceptance_number)
            if payload['rows']:
                lead = self.dg._row_to_lead(region, feed, payload['rows'][0])
                _, detail_soup = self.scraper.fetch_html(lead['source_url'])
                self.assertIsNotNone(detail_soup)
                self.assertGreater(len(detail_soup.find_all('table')), 0)
                self.assertTrue(
                    self.dg._validate_detail(detail_soup, feed, payload['rows'][0])
                )
                detail_checked += 1
        self.assertEqual(detail_checked, len(region['feeds']))


if __name__ == '__main__':
    unittest.main()