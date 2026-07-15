# -*- coding: utf-8 -*-
"""肇庆环评公示适配器。

通过 gkmlpt 公开 GET JSON API 获取列表（单页全量模式），详情页 HTML 内嵌
window._CONFIG.DETAIL JSON，含结构化表格和附件链接。
"""
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.eia import utils
from scraper.eia.regions import (
    _ZHAOQING_API_URL,
    _ZHAOQING_APP_URL,
    _ZHAOQING_DETAIL_RE,
    _ZHAOQING_FULL_THRESHOLD,
)
from scraper.eia.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class ZhaoqingAdapter(BaseAdapter):
    """肇庆环评采集适配器：gkmlpt JSON API + HTML 内嵌 DETAIL JSON。"""

    def __init__(self, scraper):
        super().__init__(scraper)
        self.lookback_days = getattr(scraper, 'zhaoqing_lookback_days', 3)

    def scrape_page(self, region, page):
        """gkmlpt API 为单页全量模式（page≥2 返回 404），在第一页内完成所有采集。"""
        if page > 1:
            return []

        start_date = self._resolve_start_date(region['name'])
        results = []
        for feed in region['feeds']:
            api_url = _ZHAOQING_API_URL.format(column_id=feed['column_id'])
            response = self.scraper.fetch(api_url, extra_headers={'Accept': 'application/json'})
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
                self.scraper._check_pause_and_stop()
                article_date = datetime.fromtimestamp(article['date']).date() if article.get('date') else None
                if start_date is not None and (article_date is None or article_date < start_date):
                    continue

                detail = self._fetch_detail(article['url'])
                if detail is None:
                    logger.warning('[eia] 肇庆详情获取失败，保留列表核心字段: %s', article['url'])
                    results.append({
                        'project_name': article.get('title', ''),
                        'announcement_type': feed['announcement_type'],
                        'region': region['name'],
                        'publish_date': datetime.fromtimestamp(article['date']) if article.get('date') else None,
                        'source_url': article['url'],
                    })
                    continue

                item = self._row_to_lead(article, detail, feed['announcement_type'], region['name'])
                results.append(item)

        mode = '全量' if start_date is None else f'{self.lookback_days}天增量'
        logger.info('[eia] 肇庆(%s)采集到 %d 条结果', mode, len(results))
        return results

    # ------------------------------------------------------------------
    # 首次全量 / 增量策略
    # ------------------------------------------------------------------
    def _resolve_start_date(self, region_name):
        """DB 中肇庆 lead 少于阈值 → 全量采集；达到阈值 → 增量窗口。"""
        threshold = _ZHAOQING_FULL_THRESHOLD
        scraper = self.scraper
        if scraper.app is not None:
            try:
                from app.models import Lead
                with scraper.app.app_context():
                    count = Lead.query.filter(
                        Lead.source_type == 'eia',
                        Lead.region == region_name,
                    ).count()
                if count >= threshold:
                    logger.info('[eia] 肇庆已有 %d 条历史数据(≥%d)，使用 %d 天增量窗口',
                                count, threshold, self.lookback_days)
                    return datetime.now().date() - timedelta(days=self.lookback_days)
                else:
                    logger.info('[eia] 肇庆仅 %d 条历史数据(<%d)，全量抓取（无日期过滤）',
                                count, threshold)
                    return None
            except Exception as exc:
                logger.warning('[eia] 肇庆 DB 查询异常，回退到增量窗口: %s', exc)
        return datetime.now().date() - timedelta(days=self.lookback_days)

    # ------------------------------------------------------------------
    # 详情获取
    # ------------------------------------------------------------------
    def _fetch_detail(self, url):
        """从详情页 HTML 提取内嵌的 window._CONFIG.DETAIL JSON。"""
        response = self.scraper.fetch(url)
        if response is None:
            return None
        html_text = response.text
        m = _ZHAOQING_DETAIL_RE.search(html_text)
        if not m:
            logger.error('[eia] 肇庆详情页未找到 DETAIL JSON: %s', url)
            return None
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error('[eia] 肇庆详情 DETAIL JSON 解析失败: %s - %s', url, exc)
            return None

    # ------------------------------------------------------------------
    # 行映射
    # ------------------------------------------------------------------
    def _row_to_lead(self, article, detail, announcement_type, region_name):
        """将肇庆 API 条目 + DETAIL JSON 表格映射为 lead 字段。"""
        content_html = detail.get('content', '')
        kv = {}
        content_soup = None
        if content_html:
            content_soup = BeautifulSoup(content_html, 'lxml')
            kv = utils.extract_kv_tables(content_soup)

        publish_date = datetime.fromtimestamp(article['date']) if article.get('date') else None

        project_name = kv.get('项目名称') or article.get('title', '')
        buyer_name = kv.get('建设单位', '')
        buyer_address = kv.get('建设地点', '')
        agency_name = kv.get('环评单位') or kv.get('环评机构', '')
        env_doc_type = kv.get('环评文件类型', '')

        full_text = content_soup.get_text('\n', strip=True) if content_soup else ''
        phone = utils.extract_government_phone(full_text)

        source_files = []
        if content_soup:
            for a in content_soup.find_all('a', href=True):
                href = a['href']
                name = a.get_text(strip=True) or ''
                if utils.ATTACHMENT_EXT_RE.search(href) or utils.ATTACHMENT_EXT_RE.search(name):
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
        approval_number = kv.get('审批文号') or kv.get('批复文号')
        if approval_number:
            result['approval_number'] = approval_number
        return result