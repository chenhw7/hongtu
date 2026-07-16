# -*- coding: utf-8 -*-
"""跨采集器共享的纯函数工具（无外部依赖，便于单元测试）。"""
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

# 附件扩展名匹配
_ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|docx?|xlsx?|zip|rar|7z|txt)(\?.*)?$', re.IGNORECASE)

# 文件名非法字符
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def parse_date(value):
    """解析日期字符串，返回 date 对象。

    支持格式：YYYY-MM-DD、YYYY年MM月DD日、MM-DD（补当年）、YYYY/MM/DD
    """
    if not value:
        return None
    value = str(value).strip().replace('/', '-').replace('年', '-').replace('月', '-').replace('日', '')
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # MM-DD 格式（无年份），自动补当前年份
    try:
        return datetime.strptime(f'{datetime.now().year}-{value}', '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_datetime(value):
    """解析 "YYYY-MM-DD HH:MM:SS" 字符串，返回 (date, 'HH:MM') 二元组。"""
    if not value:
        return None, None
    value = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(value, fmt)
            time_str = dt.strftime('%H:%M') if fmt != '%Y-%m-%d' else None
            return dt.date(), time_str
        except ValueError:
            continue
    return None, None


def parse_amount(value):
    """金额解析：'1,234.56' -> 1234.56"""
    if not value:
        return None
    try:
        return float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return None


def extract_attachments(soup, base_url):
    """从 BeautifulSoup 中提取附件下载链接。

    匹配常见文档扩展名（pdf/doc/docx/xls/xlsx/zip/rar/7z/txt），
    返回 list[dict]，每项包含 name 和 url。
    """
    attachments = []
    seen_urls = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith('javascript:') or href.startswith('#'):
            continue
        if not _ATTACHMENT_EXT_RE.search(href):
            continue
        full_url = href if href.startswith('http') else urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        name = a.get_text(strip=True) or urlparse(full_url).path.rsplit('/', 1)[-1] or 'attachment'
        attachments.append({'name': name[:200], 'url': full_url})
    return attachments


def safe_filename(name, default='attachment'):
    """清理文件名中的路径分隔符等危险字符，防止路径穿越。"""
    name = (name or '').strip()
    name = _UNSAFE_FILENAME_RE.sub('_', name)
    name = name.strip('. ')
    return name[:150] if name else default
