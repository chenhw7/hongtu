# -*- coding: utf-8 -*-
"""肇庆 gkmlpt 调研4：在 JS bundle 里找列表API + 尝试 southcn gkml 通用列表接口。"""
import re
import httpx

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
H = {'User-Agent': UA}
ORIGIN = 'https://www.zhaoqing.gov.cn'


def get(url):
    try:
        return httpx.get(url, headers=H, timeout=30, follow_redirects=True, verify=False)
    except Exception as e:
        print('ERR', url, e); return None


# 拉取 JS bundle，搜 API 路径
for js in ['/gkmlpt/gkml/pc/js/content.0c51eb50.js',
           '/gkmlpt/gkml/pc/js/chunk-common.c1553651.js']:
    r = get(ORIGIN + js)
    if r is None or r.status_code != 200:
        print('js miss', js, None if r is None else r.status_code); continue
    print('=== ', js, 'len', len(r.text))
    paths = set(re.findall(r'["\'`](/[A-Za-z0-9_\-/]*(?:list|List|content|article|column|Column|catalog|api|query|Article)[A-Za-z0-9_\-/]*)["\'`]', r.text))
    for p in sorted(paths):
        if len(p) < 70:
            print('   path:', p)
    # 模板字符串拼接的路由
    for m in set(re.findall(r'(gkmlpt/[A-Za-z0-9_/${}.\-]{3,50})', r.text)):
        print('   tmpl:', m)

# southcn gkml 平台常见列表页 URL（catalogId 用 content 路径里的 3148）
for u in [
    ORIGIN + '/zqhjj/gkmlpt/list/3148.html',
    ORIGIN + '/zqhjj/gkmlpt/list/3148',
    ORIGIN + '/zqhjj/gkmlpt/index/3148',
    ORIGIN + '/zqhjj/gkmlpt/index?catalogId=3148',
    ORIGIN + '/zqhjj/gkmlpt/gkml/list?catalogId=3148',
    ORIGIN + '/zqhjj/gkmlpt/api/list?catalogId=3148&pageNo=1&pageSize=10',
]:
    r = get(u)
    if r is not None:
        hit = ','.join(k for k in ('受理', '项目名称', '环境影响', 'post_') if k in r.text)
        print(f'try {r.status_code} len={len(r.text)} hit=[{hit}] {u[-48:]}')
