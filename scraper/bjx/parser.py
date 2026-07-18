# -*- coding: utf-8 -*-
"""bjx HTML DOM 解析（列表页 + 详情页 → Lead dict）。

北极星环保网（bjx.com.cn）环保频道和招投标栏目页面结构。
列表页为 SSR（服务端渲染），详情页包含招标/项目公告全文。
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.bjx.utils import clean_bjx_text, parse_bjx_date, extract_bjx_phone

logger = logging.getLogger(__name__)


def _make_soup(html):
    """创建 BeautifulSoup 对象。"""
    try:
        return BeautifulSoup(html, 'lxml')
    except Exception:
        return BeautifulSoup(html, 'html.parser')


def _resolve_url(href, base_url):
    """将相对 URL 转为绝对 URL。"""
    if not href:
        return ''
    href = href.strip()
    if href.startswith(('http://', 'https://')):
        return href
    return urljoin(base_url, href)


def _extract_date_from_text(text):
    """从文本中提取日期字符串。"""
    if not text:
        return ''
    m = re.search(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?', text)
    if m:
        return m.group(0)
    # 中文日期
    m = re.search(r'\d{4}年\d{1,2}月\d{1,2}日', text)
    if m:
        return m.group(0)
    return ''


def parse_list_page(html, base_url='https://huanbao.bjx.com.cn'):
    """解析列表页 HTML，提取招标/项目条目。

    北极星环保网列表页常见结构：
    - <ul class="list"> / <div class="news-list"> 中的 <li> 条目
    - 表格形式的列表
    - fallback：含日期模式的链接

    Args:
        html: 列表页 HTML 字符串
        base_url: 基础 URL，用于拼接相对路径

    Returns:
        list[dict]: 每项包含 project_name, source_url, publish_date,
                    announcement_type（可能为空）
    """
    if not html:
        return []

    soup = _make_soup(html)
    results = []

    # 策略 1：常见列表容器
    list_containers = soup.select(
        'ul.list li, ul.news-list li, ul.result-list li, '
        'div.list-item, div.news-item, div.result-item, '
        'div.list li, div.article-list li, div.info-list li, '
        'ul.cc-list li, div.cc-list div.item, '
        'div.news_list li, div.newslist li, '
        'div.content-list li, div.article-list-box li'
    )

    for item in list_containers:
        lead = _parse_list_item(item, base_url)
        if lead and lead.get('project_name'):
            results.append(lead)

    if results:
        return results

    # 策略 2：表格行
    table_rows = soup.select('table tbody tr')
    for row in table_rows:
        lead = _parse_table_row(row, base_url)
        if lead and lead.get('project_name'):
            results.append(lead)

    if results:
        return results

    # 策略 3：fallback — 查找所有含日期的链接
    results = _fallback_parse_links(soup, base_url)
    return results


def _parse_list_item(item, base_url):
    """解析单个列表项（li/div）。"""
    lead = {}

    # 标题 + 链接
    title_tag = item.select_one('a[href]')
    if title_tag:
        lead['project_name'] = clean_bjx_text(title_tag.get_text())
        lead['source_url'] = _resolve_url(title_tag.get('href', ''), base_url)

    # 日期 — 查找含日期文本的元素
    date_el = item.select_one('.date, .time, span.date, em, .pub-date, .publish-date, span.r')
    if date_el:
        date_text = date_el.get_text(strip=True)
    else:
        date_text = _extract_date_from_text(item.get_text())

    pub_date, pub_time = parse_bjx_date(date_text)
    if pub_date:
        lead['publish_date'] = pub_date
    if pub_time:
        lead['publish_time'] = pub_time

    # 类型标签（招标/中标/变更 等）
    type_el = item.select_one('.type, .tag, .label, .category, span[class*="type"], em.tag')
    if type_el:
        lead['announcement_type'] = clean_bjx_text(type_el.get_text())[:50]

    return lead


def _parse_table_row(row, base_url):
    """解析表格行。"""
    cells = row.select('td')
    if len(cells) < 2:
        return {}

    lead = {}

    link_tag = row.select_one('a[href]')
    if link_tag:
        lead['project_name'] = clean_bjx_text(link_tag.get_text())
        lead['source_url'] = _resolve_url(link_tag.get('href', ''), base_url)

    for cell in cells:
        text = cell.get_text(strip=True)
        date_match = re.search(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', text)
        if date_match:
            pub_date, pub_time = parse_bjx_date(date_match.group(0))
            if pub_date:
                lead['publish_date'] = pub_date
            break

    return lead


def _fallback_parse_links(soup, base_url):
    """Fallback：从所有链接中提取含日期的条目。"""
    results = []
    date_pattern = re.compile(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}')

    for a_tag in soup.select('a[href]'):
        text = clean_bjx_text(a_tag.get_text())
        if not text or len(text) < 5:
            continue

        href = a_tag.get('href', '')
        if not href or href in ('#', '/', 'javascript:void(0)'):
            continue

        parent = a_tag.parent
        parent_text = parent.get_text() if parent else ''
        date_match = date_pattern.search(parent_text)

        if date_match:
            pub_date, pub_time = parse_bjx_date(date_match.group(0))
            lead = {
                'project_name': text[:500],
                'source_url': _resolve_url(href, base_url),
            }
            if pub_date:
                lead['publish_date'] = pub_date
            if pub_time:
                lead['publish_time'] = pub_time
            results.append(lead)

    return results


def parse_detail_page(html, base_url='https://huanbao.bjx.com.cn'):
    """解析详情页 HTML，提取联系信息和附件。

    提取字段：
    - buyer_name: 采购/建设单位
    - contact_person: 联系人
    - phone: 电话
    - budget_amount: 预算金额
    - region: 地域
    - agency_name: 代理机构
    - bidding_number: 招标编号
    - deadline: 截止日期
    - attachments: 附件链接列表

    Args:
        html: 详情页 HTML 字符串
        base_url: 基础 URL

    Returns:
        dict: 提取到的字段（可能部分为空）
    """
    if not html:
        return {}

    soup = _make_soup(html)
    lead = {}

    # 提取正文内容区域
    content_area = soup.select_one(
        'div.content, div.article-content, div.detail-content, '
        'div.news-content, div.info-content, div.main-content, '
        'div#content, div.post-content, div.entry-content, '
        'div.text, div.article_con, div.art_content, '
        'div.TRS_Editor, div.trs_editor_view'
    )
    if not content_area:
        content_area = soup.body if soup.body else soup

    full_text = content_area.get_text(separator='\n') if content_area else ''

    # 构建键值对映射
    kv_map = _extract_key_value_pairs(full_text)

    # buyer_name — 采购/建设单位
    for key in ('采购人', '采购单位', '建设单位', '招标人', '业主单位', '甲方',
                '招标人名称', '采购人名称', '业主'):
        if key in kv_map:
            lead['buyer_name'] = kv_map[key][:200]
            break

    # contact_person — 联系人
    for key in ('联系人', '项目联系人', '招标联系人', '招标代理机构联系人',
                '采购人联系人'):
        if key in kv_map:
            lead['contact_person'] = kv_map[key][:100]
            break

    # phone — 电话
    for key in ('联系电话', '电话', '联系方式', '咨询电话', '招标电话',
                '联系方式', '电 话', '电话/传真'):
        if key in kv_map:
            lead['phone'] = kv_map[key][:100]
            break
    if not lead.get('phone'):
        phone = extract_bjx_phone(full_text)
        if phone:
            lead['phone'] = phone

    # budget_amount — 预算
    for key in ('预算金额', '预算', '项目预算', '采购预算', '预算金额（万元）',
                '控制价', '合同包预算金额'):
        if key in kv_map:
            lead['budget_amount'] = kv_map[key][:100]
            break
    if not lead.get('budget_amount'):
        budget_match = re.search(r'(?:预算|金额|控制价)[：:]\s*([\d,.]+)\s*(?:万?元)', full_text)
        if budget_match:
            lead['budget_amount'] = budget_match.group(0)[:100]

    # region — 地域
    for key in ('地区', '地域', '所在地区', '项目地区', '项目地址', '建设地点',
                '项目所在地', '工程地点'):
        if key in kv_map:
            lead['region'] = kv_map[key][:50]
            break

    # agency_name — 代理机构
    for key in ('代理机构', '招标代理', '招标代理机构', '采购代理'):
        if key in kv_map:
            lead['agency_name'] = kv_map[key][:200]
            break

    # agency_phone
    for key in ('代理机构联系电话', '代理机构电话', '招标代理联系电话'):
        if key in kv_map:
            lead['agency_phone'] = kv_map[key][:100]
            break

    # bidding_number — 招标编号
    for key in ('招标编号', '项目编号', '采购编号', '项目编号：', '招标文件编号',
                '招标编号：', '采购项目编号'):
        if key in kv_map:
            lead['bidding_number'] = kv_map[key][:100]
            break

    # deadline — 截止日期
    for key in ('截止时间', '投标截止时间', '开标时间', '报名截止时间',
                '投标文件递交截止时间'):
        if key in kv_map:
            lead['deadline'] = kv_map[key][:100]
            break

    # attachments — 附件链接
    attachments = []
    attachment_area = soup.select_one(
        'div.attachment, div.annex, div.file-list, div.download, '
        'div.annex_list, div.file_list'
    )
    search_area = attachment_area if attachment_area else content_area
    if search_area:
        for a_tag in search_area.select('a[href]'):
            href = a_tag.get('href', '')
            text = clean_bjx_text(a_tag.get_text())
            # 过滤附件链接（常见文件扩展名）
            if re.search(r'\.(pdf|doc|docx|xls|xlsx|zip|rar)(\?|$)', href, re.I):
                attachments.append({
                    'name': text or '附件',
                    'url': _resolve_url(href, base_url),
                })
            elif '附件' in text or '下载' in text or '招标' in text:
                if href and not href.startswith(('javascript:', '#', 'mailto:')):
                    attachments.append({
                        'name': text or '附件',
                        'url': _resolve_url(href, base_url),
                    })

    if attachments:
        lead['attachments'] = attachments

    return {k: v for k, v in lead.items() if v not in (None, '', [], {})}


def _extract_key_value_pairs(text):
    """从文本中提取 "标签：值" 模式的键值对。

    支持分隔符：冒号（中英文）、等号、破折号。
    """
    kv = {}
    if not text:
        return kv

    pattern = re.compile(
        r'([\u4e00-\u9fff\w（）()]{2,20})[：:=\-—]\s*(.+?)(?:\n|$)'
    )
    for m in pattern.finditer(text):
        key = m.group(1).strip()
        value = m.group(2).strip()
        if key and value:
            kv[key] = value

    return kv
