# -*- coding: utf-8 -*-
"""跨采集器共享的纯函数工具（无外部依赖，便于单元测试）。"""
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

# 附件扩展名匹配
_ATTACHMENT_EXT_RE = re.compile(r'\.(pdf|docx?|xlsx?|zip|rar|7z|txt)(\?.*)?$', re.IGNORECASE)

# 文件名非法字符
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')

# 项目名称中常见的阶段后缀，标准化时剥离
_STAGE_SUFFIXES = [
    '环境影响评价公示',
    '环境影响报告书公示',
    '环境影响报告表公示',
    '环评报告公示',
    '环评审批公示',
    '环评公示',
    '招标公告',
    '采购公告',
    '中标公示',
    '中标公告',
    '成交公告',
    '成交公示',
    '结果公告',
    '结果公示',
    '验收报告公示',
    '竣工验收公示',
    '验收公示',
    '更正公告',
    '终止公告',
    '竞争性磋商',
    '竞争性谈判',
    '询价公告',
    '单一来源',
    '公示',
    '公告',
]

# 按长度降序排列，确保优先匹配更长的后缀
_STAGE_SUFFIXES.sort(key=len, reverse=True)

# 预编译正则：匹配尾部阶段后缀（支持裸后缀、半角括号包裹、全角括号包裹）
# 例如同时匹配: "招标公告"、"(招标公告)"、"（招标公告）"
_SUFFIXES_ALT = '|'.join(re.escape(s) for s in _STAGE_SUFFIXES)
_STAGE_SUFFIX_PATTERN = re.compile(
    r'(?:'
    r'\(\s*(?:' + _SUFFIXES_ALT + r')\s*\)'   # 半角括号: (后缀)
    r'|\uff08\s*(?:' + _SUFFIXES_ALT + r')\s*\uff09'  # 全角括号: （后缀）
    r'|(?:' + _SUFFIXES_ALT + r')'              # 裸后缀
    r')$',
)

# 尾部残留分隔符（剥后缀后可能留下未匹配的括号/破折号等）
_TRAILING_DELIMITER_RE = re.compile(r'[\s(（\-\—:：,/，、;；·]+$')


def strip_stage_suffix(name):
    """去除项目名称尾部的阶段后缀（如'招标公告'、'环评公示'等）。

    幂等设计：先去除首尾空白，再反复剥离后缀直到不再变化。
    支持三种后缀形态：
    - 裸后缀：  "XX项目招标公告" → "XX项目"
    - 半角括号包裹："XX项目(招标公告)" → "XX项目"
    - 全角括号包裹："XX项目（招标公告）" → "XX项目"
    后缀叠加也能正确处理：
    "XX项目(环评公示)招标公告" → "XX项目"

    Args:
        name: 项目名称字符串

    Returns:
        str: 去除阶段后缀后的名称；输入为空时返回空字符串
    """
    if not name:
        return ''
    name = str(name).strip()
    prev = None
    while prev != name:
        prev = name
        name = _STAGE_SUFFIX_PATTERN.sub('', name)
        # 清理剥后缀后残留的尾部分隔符
        name = _TRAILING_DELIMITER_RE.sub('', name).strip()
    return name


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


# ---------------------------------------------------------------------------
# 项目名称相似度计算辅助
# ---------------------------------------------------------------------------

# 常见分隔符：中英文括号、破折号、冒号、斜杠、空格、中圆点等
_TOKEN_SPLIT_RE = re.compile(r'[()（）\-\—:：/\s,，、;；·]')


def tokenized_bigrams(name):
    """将名称按分隔符拆为多段，每段内部生成 2-gram，返回所有段的 2-gram 并集。

    分词策略：按括号、破折号、冒号、斜杠、空格等分隔符将名称拆成多段，
    每段内部生成 2-gram，避免跨段拼接产生虚假匹配。
    例如 "XX(污水处理厂)" 与 "污水处理厂(XX)" 分词后均为 ["XX", "污水处理厂"]，
    2-gram 集合完全相同。

    Args:
        name: 项目名称字符串

    Returns:
        set[str]: 所有 2-gram 的集合
    """
    tokens = [t for t in _TOKEN_SPLIT_RE.split(name) if len(t) >= 2]
    grams = set()
    for token in tokens:
        for i in range(len(token) - 1):
            grams.add(token[i:i + 2])
    return grams


def extract_field(obj, field):
    """从 ORM 对象或 dict 中安全提取字段值。

    支持两种数据形态：
    - dict: 通过 ``obj.get(field)`` 取值
    - ORM 对象: 通过 ``getattr(obj, field)`` 取值

    Args:
        obj: Lead ORM 对象或 dict
        field: 字段名

    Returns:
        字段值；取不到时返回空字符串
    """
    if isinstance(obj, dict):
        return obj.get(field, '') or ''
    return getattr(obj, field, '') or ''
