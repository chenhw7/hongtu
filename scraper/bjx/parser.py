# -*- coding: utf-8 -*-
"""bjx HTML DOM 解析（主站搜索页 → Lead dict）。

解析 www.bjx.com.cn/search/?kw= 返回的全站搜索结果页，
提取招标/中标相关条目，过滤无关行业新闻。
"""
import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from scraper.bjx.utils import clean_bjx_text, parse_bjx_date

logger = logging.getLogger(__name__)

# 标题白名单关键词：只保留含以下词汇的条目，过滤纯新闻/政策噪声
_TITLE_WHITELIST = (
    '招标', '中标', '采购', 'EPC', '项目', '公示', '公告',
    '预中标', '框采', '竞标', '投标', '工程',
    '中标候选人', '成交', '开标', '竞争性谈判',
    'BOT', 'BOO', 'PPP', '托管', '运营',
    '万', '亿',  # 含金额的标题通常是招标类
)

# URL 中的日期模式：/YYYYMMDD/NNNNN.shtml
_URL_DATE_RE = re.compile(r'/(\d{4})(\d{2})(\d{2})/(\d+)\.shtml')


def _title_is_relevant(title):
    """判断标题是否为有价值的招投标信息。"""
    if not title:
        return False
    return any(kw in title for kw in _TITLE_WHITELIST)


def parse_search_page(html, base_url='https://www.bjx.com.cn'):
    """解析 www.bjx.com.cn/search/?kw= 页面，提取线索。

    过滤逻辑：
    1. 只取含 .shtml + 日期路径的链接（确保是文章，不是导航）
    2. 标题必须命中白名单关键词（过滤纯新闻/政策噪声）

    Args:
        html: 搜索结果页 HTML 字符串
        base_url: 基础 URL

    Returns:
        list[dict]: 每项包含 project_name, source_url, publish_date
    """
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')

    results = []
    seen_urls = set()

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        title = a_tag.get_text(strip=True)

        # 过滤空标题和超短标题
        if not title or len(title) < 8 or len(title) > 200:
            continue

        # 只取含日期路径的 .shtml 链接
        m = _URL_DATE_RE.search(href)
        if not m:
            continue

        # 去重
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # 标题白名单过滤
        if not _title_is_relevant(title):
            continue

        # 从 URL 提取日期（返回 Python date 对象，SQLAlchemy Date 列需要）
        year, month, day, _art_id = m.groups()
        try:
            publish_date = date(int(year), int(month), int(day))
        except (ValueError, TypeError):
            continue

        results.append({
            'project_name': clean_bjx_text(title),
            'source_url': href,
            'publish_date': publish_date,
        })

    logger.debug('[bjx] 解析搜索页: 总链接 %d 个，有效线索 %d 条',
                 len(seen_urls), len(results))
    return results


# ----- 以下保留兼容接口（其他模块可能引用） -----

def parse_list_page(html, base_url='https://www.bjx.com.cn'):
    """兼容接口：委派到 parse_search_page。"""
    return parse_search_page(html, base_url)


def parse_detail_page(html, base_url='https://www.bjx.com.cn'):
    """解析详情页（当前主站通道无法访问详情页，保留接口但返回空）。"""
    return {}
