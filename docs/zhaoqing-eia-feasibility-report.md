# 肇庆市环评公示爬取可行性分析与实现报告

## 1. 背景

在 `scraper/eia.py` 的 REGIONS 注册表中，肇庆被标记为暂未接入城市，注释原文为：

> 肇庆: www.zhaoqing.gov.cn 用 gkmlpt 信息公开目录 CMS，详情页表格规整，但未找到
> 可直接翻页的受理公告列表 URL（栏目树疑似 JS 渲染），需进一步定位列表接口。

本次调研的核心目标：定位该"列表接口"，评估完整接入的技术可行性。

---

## 2. 数据源发现

### 2.1 官方平台

肇庆市生态环境局政府信息公开平台（gkmlpt）地址：

```
https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/index
```

该平台基于广东省统一的 gkmlpt（政府信息公开平台）CMS，是全省政务网站的标准框架。

### 2.2 栏目树结构

通过分析页面内嵌的 `window._CONFIG.TREE` JSON 数据，定位到环评公示栏目：

| 栏目名称 | column_id | parent_id | post_count |
|---------|-----------|-----------|------------|
| **建设项目环境影响评价信息** | 21022 | 0 | — |
| 受理公告 | 21023 | 21022 | 203 |
| 审批前公示 | 21025 | 21022 | 156 |
| 审批后公告 | 21028 | 21022 | 128 |

三个子栏目覆盖了环评公示的全生命周期（受理 → 审批前 → 审批后），数据总量 **487 条**。

---

## 3. API 接口发现（关键突破）

### 3.1 列表 API

通过逆向分析 gkmlpt 前端 JS bundle（`chunk-common.c1553651.js`），发现 `fetchPostList` 函数中的 API 模式：

```javascript
// JS 源码中的 API 拼接逻辑
var s = "".concat(r, "/gkmlpt/api/all/").concat(t, "?page=").concat(a, "&sid=").concat(d);
// 其中: r = APP_URL, t = column_id, a = Math.ceil(e/5), d = site_id(758019)
```

**实际可用 URL：**

```
https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/api/all/{column_id}?page={page}&sid=758019
```

### 3.2 API 响应结构

```json
{
  "classify": {
    "id": 21023,
    "name": "受理公告",
    "parent": 21022,
    "post_count": 203,
    "theme_count": 203
  },
  "articles": [
    {
      "id": 3255421,
      "title": "金宸农牧科技（四会）有限公司四会富硒蛋鸡产业园项目受理公告",
      "date": 1783353600,           // Unix timestamp
      "publisher": "肇庆市生态环境局",
      "classify_main_name": "受理公告",
      "url": "https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3255/post_3255421.html",
      "identifier": "11441200MB2C91453G/2026-00271"
    }
    // ... 88 articles per page
  ]
}
```

### 3.3 实测结果

| 栏目 | page=0/1 | articles/page | 时间跨度 |
|------|----------|---------------|---------|
| 受理公告 (21023) | ✅ 200 | 88 | 2026-07-07 ~ 2023-01-19 |
| 审批前公示 (21025) | ✅ 200 | 99 | 待测 |
| 审批后公告 (21028) | ✅ 200 | 75 | 待测 |

**分页限制**：page=2 及以上返回 404。API 设计为单页模式，page=0 和 page=1 返回相同内容，约覆盖 88-99 条记录。对于日常增量采集（每天只取最近几天的数据），单页足够。

---

## 4. 详情页分析

### 4.1 详情页 URL 模式

API 返回的每条 article 包含 `url` 字段：

```
https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/content/3/3255/post_3255421.html
```

实测 HTTP 200，**无需登录/Cookie**，直接 GET 可访问。

### 4.2 详情页内容结构

详情页 HTML 中内嵌 `window._CONFIG.DETAIL` JSON，包含完整内容。受理公告的典型表格结构：

| 表头 | 含义 | 对应 lead 字段 |
|------|------|---------------|
| 受理日期 | 项目受理时间 | 可辅助验证 |
| 项目名称 | 建设项目名 | `project_name` |
| 建设单位 | 项目业主 | `buyer_name` |
| 建设地点 | 项目位置 | 可辅助 |
| 环评单位 | 环评编制机构 | 可辅助 |
| 环评文件类型 | 报告书/报告表 | `announcement_type` 辅助 |
| 环评文件 | 附件链接 | `source_files` |

底部固定文字：`公告期限：自本公告发布之日起10个工作日届满，联系电话：0758-2781002。`

### 4.3 附件下载

附件 URL 模式：

```
https://www.zhaoqing.gov.cn/zqhjj/attachment/0/306/306724/3255421.pdf
```

实测 HTTP 200，**可直接下载**，无需 POST 或验证码。

---

## 5. 反爬评估

| 检测项 | 结果 | 说明 |
|--------|------|------|
| Cloudflare / 521 拦截 | ❌ 不存在 | 对比梅州的 521 问题 |
| HTTP 412 / JS 校验 | ❌ 不存在 | 对比清远的 412 问题 |
| 验证码 | ❌ 不存在 | API 和详情页均无验证码 |
| 登录要求 | ❌ 不存在 | 所有接口公开 GET |
| robots.txt | 待确认 | 需实测 `BaseScraper.fetch()` 的 robots 检查 |
| 分页深度限制 | ⚠️ page≥2 返回 404 | 但单页数据量足够覆盖增量采集 |
| 请求频率敏感度 | ⚠️ 连续请求 page=2 紧接 page=1 失败 | 建议保持 1-2s 间隔 |

**结论**：肇庆 gkmlpt 平台的反爬强度**远低于梅州(521)、清远(412)、东莞(验证码)**，属于最友好的类别。唯一限制是 API 单页模式，但这与增量采集场景完全兼容。

---

## 6. 实现方案

### 6.1 适配器选择

**推荐方案：仿广州受理 API 模式**

肇庆的 gkmlpt API 与广州受理公告 JSON API 特征高度相似：

| 特征 | 广州受理 API | 肇庆 gkmlpt API |
|------|-------------|----------------|
| 数据格式 | JSON | JSON |
| 认证要求 | 无 | 无 |
| 分页方式 | API 分页 | 单页全量 |
| 详情获取 | POST 补充 | HTML 页内 JSON |
| 表格结构 | API 字段映射 | HTML table → kv 解析 |

差异点：
- 肇庆只需 GET，不需要 POST
- 肇庆详情内容在 HTML 页内 `DETAIL` JSON，而非独立 API
- 肇庆是单页全量而非多页分页

因此需要**新写一个 `zhaoqing` 适配器**，但可大量复用现有 `_extract_kv_tables()` 和 `_parse_detail()` 逻辑。

### 6.2 REGIONS 注册

```python
'zhaoqing': {
    'name': '肇庆市',
    'list_url': 'https://www.zhaoqing.gov.cn/zqhjj/gkmlpt/index',
    'level': 'city',
    'adapter': 'zhaoqing',
    'feeds': [
        {
            'column_id': 21023,
            'announcement_type': '受理公告',
        },
        {
            'column_id': 21025,
            'announcement_type': '审批前公示',
        },
        {
            'column_id': 21028,
            'announcement_type': '审批后公告',
        },
    ],
},
```

### 6.3 适配器核心流程

```python
def _scrape_zhaoqing_page(self, keyword, page, **kwargs):
    """肇庆 gkmlpt API 适配器"""
    region = REGIONS[keyword.replace('region:', '')]
    all_leads = []
    
    for feed in region['feeds']:
        # 1. 调用列表 API（只取 page=1，覆盖全部增量）
        api_url = f"{APP_URL}/gkmlpt/api/all/{feed['column_id']}?page=1&sid={SID}"
        data = self._fetch_json(api_url)
        
        # 2. 筛选最近 N 天的记录（与 scheduler 的 max_pages 增量逻辑一致）
        recent = [a for a in data['articles'] 
                  if self._is_recent(a['date'], days=self.lookback_days)]
        
        # 3. 对每条记录取详情页
        for article in recent:
            detail = self._fetch_zhaoqing_detail(article['url'])
            # 4. 从 DETAIL JSON 提取表格 KV
            kv = self._extract_kv_tables(detail['content'])
            lead = self._zhaoqing_row_to_lead(article, kv, feed['announcement_type'])
            all_leads.append(lead)
    
    return all_leads
```

### 6.4 详情获取策略

两种可选方案：

**方案 A（推荐）：提取页面内 `window._CONFIG.DETAIL` JSON**

```
优势: 数据结构化程度高，包含 content HTML + attachments + gkml_data 元数据
实现: 用正则提取 `DETAIL:\s*({...})` → JSON 解析 → 用 _extract_kv_tables 解析 content HTML
```

**方案 B（备选）：直接 fetch_soup + _parse_detail**

```
优势: 复用现有通用解析逻辑
劣势: 需要完整渲染页面（含 JS），soup 解析可能遗漏内嵌数据
```

推荐方案 A，因为 DETAIL JSON 包含的字段比纯 HTML soup 更丰富（如 `identifier`、`classify_main_name` 等）。

### 6.5 字段映射

```python
def _zhaoqing_row_to_lead(self, article, kv, announcement_type):
    return {
        'project_name': kv.get('项目名称', article['title']),
        'buyer_name':   kv.get('建设单位', ''),
        'announcement_type': announcement_type,
        'date':         datetime.fromtimestamp(article['date']),
        'source_url':   article['url'],
        'publisher':    article.get('publisher', '肇庆市生态环境局'),
        'contact_phone': self._extract_government_phone(kv.get('联系电话', '')),
        'source_files': self._parse_zhaoqing_attachments(article, kv),
        'raw_html':     article['url'],  # 保存详情页 URL 用于快照
    }
```

### 6.6 附件处理

肇庆附件可直接 GET 下载（与东莞需 POST 不同），因此：

- **可以交给 BaseScraper 的 GET 附件下载流程**（`_save_attachments`）
- 附件 URL 从 DETAIL JSON 的 `content` HTML 中提取（`<a class="nfw-cms-attachment">` 标签）

---

## 7. 增量采集策略

### 7.1 日常运行

scheduler 每日 08:00 运行，`max_pages=3`。对于肇庆：

- API 只需调用 1 次（page=1），覆盖约 88-99 条记录
- 按日期筛选，只取最近 2-3 天的记录（通常 ≤ 10 条）
- 每条取详情页 1 次，总请求量 ≤ 3 + 10 = 13 次

### 7.2 历史补录

API page=1 覆盖从 2023-01 到当前的全部数据（88 条受理公告）。如需更早数据（203 条全量），需要：
- 方案 1：多次运行，每次取一批，直到去重不再产生新 lead
- 方案 2：调研 page=2 404 的原因，可能是缺少必要参数

**建议**：先只接入增量采集，历史补录作为后续优化。

---

## 8. 需进一步验证的项

| 项目 | 验证方式 | 优先级 |
|------|---------|--------|
| 审批前公示/审批后公告详情页表格结构 | curl 实取 1 条详情 | 高 |
| 审批后公告是否有"批复文号"字段 | 同上 | 高 |
| robots.txt 是否允许爬取 gkmlpt | `curl https://www.zhaoqing.gov.cn/robots.txt` | 中 |
| API page=2 404 的根因（参数缺失？限流？设计） | 不同间隔重试 + 参数测试 | 中 |
| 审批前公示详情页是否有联系电话 | 同上 | 低 |

---

## 9. 工作量估算

| 任务 | 预估 | 说明 |
|------|------|------|
| REGIONS 注册 + 配置 | 0.5h | 仿珠海多 feeds 格式 |
| _scrape_zhaoqing_page 适配器 | 1h | API 调用 + 日期筛选 |
| _fetch_zhaoqing_detail | 1h | DETAIL JSON 提取 |
| _zhaoqing_row_to_lead 字段映射 | 0.5h | KV → lead 字段 |
| 单元测试 | 2h | 仿 test_eia.py 中广州/东莞测试模式 |
| 实测验证（live test） | 0.5h | 3 个栏目各取 1 条验证 |
| **合计** | **~5.5h** | 不含历史补录调研 |

---

## 10. 结论

**可行性：✅ 完全可行**

原注释中的两大障碍已全部解决：
1. ✅ "未找到可直接翻页的受理公告列表 URL" → 已定位 `/gkmlpt/api/all/{column_id}` JSON API
2. ✅ "栏目树疑似 JS 渲染" → 栏目树以 JSON 嵌入 `window._CONFIG.TREE`，API 使用固定 column_id，无需渲染

肇庆 gkmlpt 的反爬强度为最低档（无验证码、无 JS 校验、无登录），API 和详情页均为公开 GET，附件可直接下载。接入难度低于现有已接入的大部分城市。

唯一约束是 API 单页模式（page≥2 返回 404），但对日常增量采集场景无影响——page=1 已覆盖 88 条记录，时间跨度约 3.5 年，增量采集只需其中最近几天的数据。

**建议优先级：高** — 数据完整、反爬友好、实现简单，应优先于梅州（需反 Cloudflare）和清远（需反 412）接入。
