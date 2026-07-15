# -*- coding: utf-8 -*-
"""肇庆 gdeei 统一环评平台 API 调研。"""
import json
import httpx

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
H = {'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9',
     'Referer': 'https://www.zhaoqing.gov.cn/'}


def show(url, note, params=None, method='GET', body=None):
    try:
        if method == 'GET':
            r = httpx.get(url, headers=H, params=params, timeout=25, follow_redirects=True, verify=False)
        else:
            r = httpx.post(url, headers={**H, 'Content-Type': 'application/json'}, params=params,
                           json=body, timeout=25, follow_redirects=True, verify=False)
    except Exception as e:
        print(f'[{note}] ERR {e}'); return None
    print(f'[{note}] {r.status_code} len={len(r.text)} ct={r.headers.get("content-type")}')
    print('  body head:', r.text[:600].replace('\n', ' '))
    try:
        return r.json()
    except Exception:
        return None


base = 'https://www-app.gdeei.cn/gdeepub/front/dal/ent'
# 1) 原样
show(base + '/list', 'list?areaCode=441200', params={'areaCode': '441200'})
# 2) 带常见分页参数
for extra in [{'areaCode': '441200', 'pageNo': 1, 'pageSize': 10},
              {'areaCode': '441200', 'pageNum': 1, 'pageSize': 10},
              {'areaCode': '441200', 'page': 1, 'rows': 10}]:
    show(base + '/list', f'list {extra}', params=extra)
