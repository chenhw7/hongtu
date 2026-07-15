# -*- coding: utf-8 -*-
"""静态 HTML 环评公示适配器。

覆盖约 15 个城市：广东、江门、河源、湛江、韶关、揭阳、汕尾、阳江、汕头、
惠州、佛山、中山、云浮、茂名（单栏目）以及珠海、广州审批前/批复（多栏目 feeds）。
"""
import logging
from urllib.parse import urljoin

from scraper.eia import utils
from scraper.eia.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class StaticAdapter(BaseAdapter):
    """静态 HTML 页面采集适配器。

    支持两种模式：
    - 单栏目：region 直接配置 list_url / list_selector 等字段
    - 多栏目：region['feeds'] 包含多个子栏目，每个子栏目独立分页采集
    """

    def scrape_page(self, region, page):
        """根据 region 配置自动选择单栏目或多栏目模式。"""
        if region.get('feeds'):
            return self._scrape_feeds(region, page)
        return self._scrape_single(region, page)

    # ------------------------------------------------------------------
    # 多栏目（feeds）
    # ------------------------------------------------------------------
    def _scrape_feeds(self, region, page):
        """采集由多个纯静态 HTML 栏目组成的地区。"""
        results = []
        for feed in region['feeds']:
            rows = self._scrape_single(
                feed,
                page,
                region_name=region['name'],
                announcement_type=feed.get('announcement_type'),
            )
            if rows is None:
                return None
            results.extend(rows)
        return results

    # ------------------------------------------------------------------
    # 单栏目核心逻辑
    # ------------------------------------------------------------------
    def _scrape_single(self, source, page, region_name=None, announcement_type=None):
        """采集一个静态 HTML feed 的单个逻辑页。

        source 可以是一个 region 或一个 feed 子栏目。
        """
        list_url = self._list_url_for_page(source, page)
        html_text, soup, status_code = self.fetch_html_with_status(list_url)

        if status_code == 404:
            if page > 1:
                return []
            logger.error('[eia] 静态栏目首页不存在，可能已迁移: %s', list_url)
            return None
        if soup is None:
            logger.error('[eia] 静态列表请求失败: %s', list_url)
            return None

        items = self._extract_items(source, soup, list_url)
        if items is None:
            return None
        if not items:
            return []

        results = []
        for item_node in items:
            self.scraper._check_pause_and_stop()
            a = item_node.find('a')
            if a is None or not a.get('href'):
                continue
            detail_url = urljoin(list_url, a['href'])
            title = (a.get('title') or a.get_text(strip=True)).strip()
            date_node = item_node.select_one(source.get('date_selector', 'span'))
            publish_date = utils.parse_date(date_node.get_text(strip=True) if date_node else '')
            item_type = announcement_type or source.get('announcement_type') or utils.classify_category(title)

            detail_html, detail_soup, detail_status = self.fetch_html_with_status(detail_url)
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

            item = self.parse_detail(detail_soup)
            item['project_name'] = item.get('project_name') or title
            item['announcement_type'] = item_type
            item['region'] = region_name or source['name']
            item['publish_date'] = publish_date
            item['source_url'] = detail_url
            item['attachments'] = utils.extract_attachments(detail_soup, detail_url)
            item['_raw_html'] = detail_html
            results.append(item)

        return results

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _list_url_for_page(source, page):
        """构造分页列表 URL。"""
        if page == 1:
            return source['list_url']
        page_pattern = source.get('page_url_pattern')
        if not page_pattern:
            page_pattern = source['list_url'].replace('index.html', 'index_{page}.html')
        return page_pattern.format(page=page)

    @staticmethod
    def _extract_items(source, soup, list_url):
        """从列表页提取条目节点列表。"""
        containers = soup.select(source['list_selector'])
        if not containers:
            logger.error('[eia] 静态列表 selector 失效: %s - %s', list_url, source['list_selector'])
            return None
        # 非 ul/li 结构：list_selector 直接选择条目元素
        if source.get('item_selector'):
            return containers
        # ul/li 结构：选择 li 最多的容器
        main_ul = max(containers, key=lambda u: len(u.find_all('li')))
        return main_ul.find_all('li')