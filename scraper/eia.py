# -*- coding: utf-8 -*-
"""环评公示采集：省级/市级生态环境部门"建设项目环境影响评价"信息公开列表

这是建设项目从"立项"到"开工"链条上最早的公开信号（受理公告 -> 审批前公示 ->
批复/审批后公告），覆盖工业/市政/道路等各类建设项目，比政府采购中标公告更早发现
潜在的管道/给排水材料需求方（建设单位）。

已验证的两个数据源均为纯静态服务端渲染HTML（无JS/无API，无验证码/签名反爬），
分页规律与 ccgp/gdgpo 一致：第1页为 index.html，第N页(N>=2)为 index_{N}.html，
超出实际页数时返回 404（视为"无更多结果"，而非请求被拦截，不触发反爬等待）。

- 广东省级：广东省生态环境厅"建设项目环评审批公示"栏目
  https://gdee.gd.gov.cn/jsxmsp3189/index.html
  页面上有多个 <ul class="i_list">，其中部分是"最新10条"侧栏小组件（不随翻页
  变化），真正分页的是 li 数量最多的那个（合并了受理公告/审批前公示/批复公告
  三类，按日期排列），因此统一取 li 数量最多的 ul 作为列表来源。
- 江门市级：江门市生态环境局"建设项目环境影响评价信息"栏目
  http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index.html
  容器是 <ul class="infoList">，同样是三类公告混合的分页列表。

新增城市时只需在 REGIONS 里追加一项（需先实测该城市网站的 list_url/分页规律/
列表容器选择器，不能凭空套用模板，不同地市网站不一定是同一套模板）。

详情页三种类型（受理公告/审批前公示/批复公告）模板不同，但均以 <table> 承载
结构化字段，已用统一的 _extract_kv_tables() 结构化优先提取，正文里的建设地点/
联系电话用正则兜底补充（结构化优先+正则兜底，与 ccgp/gdgpo 一致的做法）。

**重要限制**：公示页面公开的"联系电话"是生态环境主管部门的公众咨询电话（公示
期内提意见/申请听证用），不是建设单位的直接联系方式——环评公示本身不公开建设
单位联系人和电话。这个号码存入 Lead.phone 仅供核实项目真实性使用，跟进时需要
通过企查查/天眼查等渠道另行查找建设单位联系人，不代表能联系到建设单位本人。
"""
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# 数据源注册表：新增城市时在此追加一项即可复用同一套解析逻辑
REGIONS = {
    'guangdong': {
        'name': '广东省',
        'list_url': 'https://gdee.gd.gov.cn/jsxmsp3189/index.html',
        'page_url_pattern': 'https://gdee.gd.gov.cn/jsxmsp3189/index_{page}.html',
        'list_selector': 'ul.i_list',
    },
    'jiangmen': {
        'name': '江门市',
        'list_url': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index.html',
        'page_url_pattern': 'http://www.jiangmen.gov.cn/bmpd/jmssthjj/zdlyxxgk/jsxmhjyxpjxx/index_{page}.html',
        'list_selector': 'ul.infoList',
    },
}

_ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|doc|docx|xls|xlsx|zip|rar|7z|txt)(\?|$)', re.IGNORECASE)


class EiaScraper(BaseScraper):
    source_type = 'eia'
    base_url = 'https://gdee.gd.gov.cn/jsxmsp3189/'

    def default_keywords(self):
        """生成默认的 "region:地区代码" 伪关键词，覆盖所有已配置数据源"""
        return [f'region:{key}' for key in REGIONS]

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

        list_url = region['list_url'] if page == 1 else region['page_url_pattern'].format(page=page)
        _, soup = self.fetch_html(list_url)
        if soup is None:
            # 列表页请求失败：既可能是页码越界(404，正常终止翻页)，也可能是
            # 网络问题；两者都当作"该地区本次无更多结果"处理，不触发反爬等待
            # （静态政府网站没有观察到限流/封禁迹象，不需要 anti_scrape_wait）。
            return []

        uls = soup.select(region['list_selector'])
        if not uls:
            return []
        main_ul = max(uls, key=lambda u: len(u.find_all('li')))
        items = main_ul.find_all('li')
        if not items:
            return []

        results = []
        for li in items:
            a = li.find('a')
            if a is None or not a.get('href'):
                continue
            detail_url = urljoin(list_url, a['href'])
            title = (a.get('title') or a.get_text(strip=True)).strip()
            span = li.find('span')
            publish_date = self._parse_date(span.get_text(strip=True) if span else '')
            announcement_type = self._classify_category(title)

            detail_html, detail_soup = self.fetch_html(detail_url)
            if detail_soup is None:
                continue

            item = self._parse_detail(detail_soup)
            item['project_name'] = item.get('project_name') or title
            item['announcement_type'] = announcement_type
            item['region'] = region['name']
            item['publish_date'] = publish_date
            item['source_url'] = detail_url
            item['attachments'] = self._extract_attachments(detail_soup, detail_url)
            item['_raw_html'] = detail_html
            results.append(item)

        return results

    @staticmethod
    def _parse_date(text):
        text = (text or '').strip()
        for fmt in ('%Y-%m-%d', '%Y年%m月%d日'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
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

        project_name = kv.get('项目名称', '')
        buyer_name = kv.get('建设单位') or kv.get('行政相对人名称') or ''
        buyer_address = kv.get('建设地点', '')
        agency_name = kv.get('环评机构') or kv.get('环评单位') or ''

        if not buyer_address:
            m = re.search(r'位于([^，。；\n]{4,50})', full_text)
            if m:
                buyer_address = m.group(1).strip()

        # 这里的电话是生态环境主管部门的公众咨询电话，不是建设单位的直接联系
        # 方式，见模块顶部说明。
        phone = ''
        phone_m = re.search(r'联系电话[：:]\s*([0-9\-，,、\s]{5,40})', full_text)
        if phone_m:
            phone = re.split(r'传\s*真', phone_m.group(1))[0].strip().rstrip('，,')

        return {
            'project_name': project_name,
            'buyer_name': buyer_name,
            'buyer_address': buyer_address,
            'agency_name': agency_name,
            'phone': phone,
        }

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
