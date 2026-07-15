# -*- coding: utf-8 -*-
"""肇庆 gkmlpt 调研：定位受理公告/审批前/审批后列表URL与结构。用完即删。"""
import re
import httpx
from bs4 import BeautifulSoup

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
H = {'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}


def g(url, note=''):
    try:
        r = httpx.get(url, headers=H, timeout=25, follow_redirects=True, verify=False)
    except Exception as e:
        print(f'[{note}] ERR {e}'); return None
    print(f'[{note}] {r.status_code} len={len(r.text)} {url}')
    return r


# 1) 从已知详情页抓侧边栏所有链接，找“受理公告/审批前公示/审批后公告”栏目URL
r = g('https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3148/post_3148466.html', '详情页')
if r is not None:
    soup = BeautifulSoup(r.text, 'lxml')
    print('--- 侧边栏/导航链接（含 list/catalog/栏目名） ---')
    for a in soup.find_all('a', href=True):
        t = a.get_text(strip=True)
        h = a['href']
        if any(k in t for k in ('受理公告', '审批前公示', '审批后公告', '建设项目环境影响评价')) \
           or any(k in h for k in ('/list', 'gkmlpt/index', 'catalog', 'column', 'channel')):
            print(f'   {t[:24]!r:28} => {h[:110]}')
    # 找页面里的 JS 变量 catalogId / columnId
    for m in set(re.findall(r'(catalog[A-Za-z]*\s*[=:]\s*["\']?\w+|column[A-Za-z]*\s*[=:]\s*["\']?\w+|"[0-9a-f]{4,}"|/list/[\w/]+)', r.text)):
        if len(m) < 60:
            print('   js:', m)

# 2) gkmlpt 目录首页，找“法定主动公开内容”栏目树
r = g('https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/index', '目录首页')
if r is not None:
    soup = BeautifulSoup(r.text, 'lxml')
    for a in soup.find_all('a', href=True):
        h = a['href']
        if any(k in h for k in ('/list/', 'catalog', 'column', 'gkml')):
            print('   idx-link:', a.get_text(strip=True)[:20], '=>', h[:110])
