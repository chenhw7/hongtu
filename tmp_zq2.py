# -*- coding: utf-8 -*-
"""肇庆 gkmlpt 调研2：栏目树API + 列表URL候选。"""
import re
import httpx
from bs4 import BeautifulSoup

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
H = {'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}


def g(url, note='', ct_check=None):
    try:
        r = httpx.get(url, headers=H, timeout=25, follow_redirects=True, verify=False)
    except Exception as e:
        print(f'[{note}] ERR {e}'); return None
    hit = ''
    if ct_check and r.status_code == 200:
        hit = ' | 命中:' + ','.join(k for k in ct_check if k in r.text)
    print(f'[{note}] {r.status_code} len={len(r.text)}{hit} {url[-70:]}')
    return r


# 详情页里搜 JS 引用的脚本、api、栏目树相关
r = g('https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3148/post_3148466.html', '详情')
if r is not None:
    html = r.text
    print('--- script src ---')
    for m in re.findall(r'<script[^>]+src="([^"]+)"', html):
        print('  ', m)
    print('--- 含 list/queryColumn/catalog/tree/api 的片段 ---')
    for m in set(re.findall(r'["\']([^"\']*(?:list|List|column|Column|catalog|Catalog|tree|Tree|api|query)[^"\']*)["\']', html)):
        if 3 < len(m) < 80 and ('/' in m or 'list' in m.lower() or 'column' in m.lower()):
            print('  ', m)
    # 面包屑里的 catalogId：URL 里 content/3/3148 -> 3148 是不是受理公告
    print('--- 面包屑 ---')
    soup = BeautifulSoup(html, 'lxml')
    for sel in ['.crumbs', '.position', '.mianbaoxie', '.current-location', '#location']:
        for el in soup.select(sel):
            print('  ', sel, ':', el.get_text(' > ', strip=True)[:80])

# 列表URL候选（gkmlpt 常见规律）
cands = [
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/list/3/3148',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/list/3/3148/1.html',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/list/3/3148/index.html',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3148',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3148/',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/catalog/3148',
    'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/column/3148',
]
for u in cands:
    g(u, '候选', ct_check=['受理', '项目名称', '环境影响'])
