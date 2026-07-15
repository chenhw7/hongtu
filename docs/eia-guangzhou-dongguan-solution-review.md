# 广州、东莞环评公示采集解决方案（Review 版）

- 调研日期：2026-07-14
- 实施日期：2026-07-14
- 文档状态：第一阶段已实现并验证；第二阶段增强项待后续评审
- 涉及模块：`scraper/eia.py`、`scraper/base.py`
- 目标：解决广州、东莞环评公示页面由 JavaScript/iframe 展示、当前 `httpx` 解析不到列表的问题

## 0. 实施状态

本方案第一阶段已经落地，未引入 Playwright/Selenium 或新第三方依赖。

已修改：

- `scraper/eia.py`
  - 注册 `region:guangzhou`、`region:dongguan`。
  - 实现广州受理 JSON API、审批前静态栏目、审批公告静态栏目。
  - 实现东莞三个目录的表单 POST 列表、公开 GET 详情、最近两天增量窗口、日期/受理号分片。
  - 审批阶段缺建设单位时，使用官网精确受理号查询历史受理记录跨日期补全；不依赖两个阶段同时落入两天窗口。
  - 广州受限附件和东莞 POST 附件仅保存到 `raw_data.source_files`，不进入自动下载流程。
  - 东莞任何验证码、非 JSON、schema 异常或分片数量不守恒均作为失败处理。
  - 东莞详情仅明确 404 时保留列表核心字段；网络错误、403、5xx 或详情模板失效均使该地区失败。
- `scraper/base.py`
  - GET 请求可选返回非 200 响应，供 EIA 区分正常 404 翻页结束与真实请求失败。
  - 分页失败会继续处理其他关键词/地区，但任务最终标记为“失败”并记录失败单元，不再把部分缺数任务显示成“完成”。
  - 数据库提交只有明确的唯一约束冲突按重复跳过；其他写入故障回滚并使任务失败，避免数据丢失却显示完成。
- `app/config.py`
  - 新增东莞默认回看天数 `EIA_DONGGUAN_LOOKBACK_DAYS = 2`。
  - EIA 请求失败不使用通用 60 秒反爬等待。
- `tests/`
  - 增加广州、东莞解析 fixture、离线单元测试、内存数据库保存测试和可选官网烟雾测试。

验证结果：

- 默认离线测试发现：23 个测试通过，3 个官网测试默认跳过。
- 设置 `EIA_LIVE_TESTS=1` 后：3 个官网烟雾测试通过。
- 官网烟雾测试覆盖广州受理 API、广州两个静态栏目及详情、东莞三个目录、受理号数字域总量守恒、跨日期精确受理号查询，以及三个目录各自的公开详情身份/必需字段。
- 广州受理分页固定第一页 `total`，校验每页应有数量、页内/跨页唯一 ID；抓取期间总量漂移，或项目名、建设单位、地点、环评单位、可解析日期任一核心字段补全失败，均使该地区失败，防止静默漏数或产生空白记录。
- 东莞详情会核对项目名称、可用时核对受理号，并按公告类型验证建设单位/地点或审批文号；仅存在任意布局表格不足以判定详情有效。
- 编辑器诊断及 Python 语法检查无错误。

第二阶段仍未实施：东莞 POST 附件自动下载、历史回补入口与检查点、项目阶段历史、广州旧静态受理栏目一次性补采。

---

## 1. 结论摘要

当前 `scraper/eia.py` 中以下两条注释的结论不准确：

> 广州：网站为 JS 渲染，httpx 无法获取列表内容  
> 东莞：网站为 JS 渲染，httpx 无法获取列表内容

准确结论是：

1. **广州可以采集**。
   - 2026-03-03 起的“环评受理公告”在 Vue 页面展示，但后端有无登录、无 Cookie、无签名的公开 JSON 接口。
   - “环评审批前公示”和“环评审批公告”仍是广州市生态环境局官网的静态服务端 HTML，可直接用现有 `httpx + BeautifulSoup` 采集。
2. **东莞可以采集**。
   - 东莞官网正文嵌入了一个 iframe；iframe 内列表由公开的表单 POST 接口返回 JSON，详情是公开的服务端 HTML。
   - 接口无需登录、Cookie、Token 或签名。
   - 第 4 页起服务端要求验证码。方案不破解、不模拟验证码，而是使用官网本身提供的“日期范围”和“受理号范围”查询条件，将增量数据拆成每个结果集不超过 60 条，再读取第 1～3 页。
3. **生产采集不需要 Playwright/Selenium，也不需要新增浏览器依赖**。浏览器只用于本次调研抓取真实请求；正式实现继续使用当前项目已有的 `httpx`。
4. **广州受理报告附件不应由定时任务自动下载**。官网对下载实施图形验证码和“每 IP 总下载 30 次”限制，应保留官方详情页供人工下载，不绕过该限制。
5. 建议同时接入两市的三个阶段：
   - 受理公告
   - 审批前/拟审批公示
   - 审批决定/审批公告

因此，这不是“网站不可爬”的问题，而是当前采集器只支持静态列表、尚未为公开 JSON/iframe 数据源实现适配器的问题。

---

## 2. 调研和验证方法

本次不是根据页面外观或 URL 猜测，已完成以下验证：

- 从两市生态环境局官方入口定位真实栏目。
- 在浏览器中记录页面实际发出的 XHR/fetch 请求。
- 脱离浏览器后，用普通 HTTP 请求重新调用列表和详情接口。
- 验证是否依赖 Cookie、Token、Referer、签名或浏览器环境。
- 验证分页、筛选、详情字段和附件下载行为。
- 对东莞第 3、4、10 页分别查看原始响应，确认验证码边界。
- 对东莞三种公告分别验证日期范围和受理号范围筛选。
- 对广州接口分别验证列表、详情和 `pageSize=20/50/100`。

截至 2026-07-14 的实测结果见下文。总量是动态值，仅用于证明接口真实返回数据，不应写成业务常量。

---

## 3. 广州解决方案

### 3.1 官方入口和数据分流

广州市生态环境局“建设项目”栏目：

- 总入口：<https://sthjj.gz.gov.cn/hjgl/jsxm/>
- 环评受理公告：<https://sthjj.gz.gov.cn/hjgl/jsxm/hpslgg/>
- 环评审批前公示：<https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/>
- 环评审批公告：<https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/>

三个阶段目前不是同一套技术实现：

| 阶段 | 当前数据载体 | 推荐采集方式 |
|---|---|---|
| 受理公告（2026-03-03 起） | Vue SPA + 公开 JSON API | 直接调用 API |
| 审批前公示 | 广州生态环境局静态 HTML | `httpx + BeautifulSoup` |
| 审批公告 | 广州生态环境局静态 HTML | `httpx + BeautifulSoup` |

受理公告原静态栏目在 2026-03-03 发布了迁移入口：

<http://112.94.69.56:8066/#/gjhpslqkgg/index>

原静态栏目最新普通受理记录停留在 2026-03-02。故当前数据应以新系统 API 为准；原栏目只适合补采迁移前历史数据，不能继续当作实时受理源。

### 3.2 广州受理公告公开接口

#### 列表接口

```text
GET http://112.94.69.56:8066/api/hpslgl/getListPublished
```

查询参数：

| 参数 | 含义 | 示例 |
|---|---|---|
| `PROJECT_NAME` | 项目名称筛选，可空 | 空字符串 |
| `CONSTRUCTION_UNIT` | 建设单位筛选，可空 | 空字符串 |
| `pageNum` | 页码，从 1 开始 | `1` |
| `pageSize` | 每页条数 | 推荐 `100` |

实测请求：

```text
/api/hpslgl/getListPublished?PROJECT_NAME=&CONSTRUCTION_UNIT=&pageNum=1&pageSize=2
```

响应结构：

```json
{
  "data": {
    "list": [
      {
        "ID": "SLGG-...",
        "PROJECT_NAME": "...",
        "CONSTRUCTION_UNIT": "...",
        "CONSTRUCTION_LOCATION": "...",
        "ENV_ASSESSMENT_UNIT": "...",
        "ENV_DOC_TYPE": "环境影响报告表",
        "ACCEPTANCE_DATE": "2026-07-14 00:00:00",
        "PUBLISH_DATE": "2026-07-14 00:00:00",
        "FILELIST": "[...]",
        "REMARK": "公告期限……联系电话……"
      }
    ],
    "total": 688
  },
  "code": 0
}
```

2026-07-14 实测：

- `code=0`
- `total=688`
- `pageSize=20` 返回 20 条
- `pageSize=50` 返回 50 条
- `pageSize=100` 返回 100 条
- 第一条为当天发布的项目，项目名称、建设单位、建设地点、环评单位、发布日期均完整

接口用普通 HTTP 请求即可成功，无需：

- 登录
- Cookie
- Token
- Authorization
- Referer
- 自定义签名
- 浏览器执行 JavaScript

#### 详情接口

```text
POST http://112.94.69.56:8066/api/hpslgl/detail
Content-Type: application/json

{"id":"SLGG-..."}
```

实测 HTTP 状态为 `201 Created`，响应体 `code=0`，`data` 返回完整记录；实现按任意成功的 2xx 状态接收，并继续严格校验业务字段。人可访问的官方详情路由为：

```text
http://112.94.69.56:8066/#/hpslzs/index?id=<ID>
```

建议把上述前端详情路由写入 `Lead.source_url`，而不是把 API URL 当作原文地址。

#### 字段映射

| 广州 API 字段 | `Lead` 字段/处理 |
|---|---|
| `ID` | 放入 `raw_data.source_record_id` |
| `PROJECT_NAME` | `project_name` |
| `CONSTRUCTION_UNIT` | `buyer_name` |
| `CONSTRUCTION_LOCATION` | `buyer_address` |
| `ENV_ASSESSMENT_UNIT` | `agency_name` |
| `PUBLISH_DATE`，缺失时 `ACCEPTANCE_DATE` | `publish_date` |
| 固定值 | `announcement_type = 受理公告` |
| 固定值 | `region = 广州市` |
| `REMARK` 中的联系电话 | `phone`，但必须标注为政府咨询电话 |
| `FILELIST` | 保存在 `raw_data.source_files`，首期不自动下载 |

`FILELIST` 是 JSON 字符串，需做第二次 `json.loads()`。解析失败时记录警告并保留原始字符串，不能使整条线索失败。

### 3.3 广州受理附件限制

这一点必须与列表采集分开处理。

列表的 `FILELIST.url` 形如：

```text
/uploads/hpslgl/<文件名>.pdf
```

实测直接 GET 该路径返回 404。前端真实下载流程是：

1. `GET /api/hpslgl/checkDownloadLimit`
2. 检查每个 IP 的累计下载上限
3. 页面弹出图形验证码
4. 验证成功后记录下载次数
5. 再由 `/api/hpslgl/download?p=<编码后的文件路径>` 下载

前端代码明确提示：

> 每个IP总下载次数限制为30次

图形验证码虽然由前端生成和校验，但它仍表达了站点明确的下载控制意图。**不应通过直接拼接下载接口或自动识别验证码绕过限制。**

首期建议：

- 正常采集项目及附件名称。
- `FILELIST` 放入 `raw_data.source_files`。
- 不把广州受理 API 附件放入现有 `attachments` 列表，避免 `BaseScraper.save_leads()` 自动下载。
- 用户需要报告时，从 `source_url` 打开官方详情页，人工完成验证码下载。

这不会影响线索发现；建设单位、项目名称、地点、环评单位和日期都已由列表 API 完整提供。

### 3.4 广州审批前公示和审批公告

这两类并非必须通过 SPA 获取，官方静态栏目仍在持续发布当天数据。

#### 审批前公示

```text
https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index.html
https://sthjj.gz.gov.cn/hjgl/jsxm/hpspqgs/index_2.html
```

#### 审批公告

```text
https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index.html
https://sthjj.gz.gov.cn/hjgl/jsxm/hpspgg/index_2.html
```

列表项结构为：

```html
<div class="conts-list">
  <span><a href="详情地址" title="标题">标题</a></span>
  <span>2026-07-14</span>
</div>
```

因此应使用：

- 列表项选择器：`div.conts-list`
- 每个被选元素直接作为一条记录
- 分页：第一页 `index.html`，后续 `index_{page}.html`

详情页为服务端 HTML，审批前公示包含标准二维表格，例如：

- 项目名称
- 建设地点
- 建设单位
- 项目概况
- 环评机构
- 主要环境影响及措施
- 公众参与情况

现有 `_extract_kv_tables()` 可以复用。

审批公告详情通常是两行多列表格，字段包括：

- 批复名称
- 审批文号
- 审批时间
- 建设单位
- 建设地点
- 批复文件

现有 `_extract_kv_tables()` 对“表头行 + 数据行”已经支持。需要补充字段别名：

- `批复名称` 可作为项目/公告补充字段
- `审批文号` 放入 `raw_data.approval_number`
- `审批时间` 可作为详情日期兜底

公告类型不应只靠标题猜测。广州三个 feed 应在配置中直接固定：

- 受理 API：`受理公告`
- `hpspqgs`：`审批前公示`
- `hpspgg`：`批复公告`

否则“关于……环境影响评价文件审批的公告”可能被当前 `_classify_category()` 错分为普通“环评公示”。

---

## 4. 东莞解决方案

### 4.1 官方入口与 iframe

东莞市生态环境局官方栏目：

- 受理情况：<https://dgepb.dg.gov.cn/zwgk/jsxm/hpspxxgk/slqk/index.html>
- 拟审批意见：<https://dgepb.dg.gov.cn/zwgk/jsxm/hpspxxgk/nspyj/index.html>
- 审批决定：<https://dgepb.dg.gov.cn/zwgk/jsxm/hpspxxgk/spjd/index.html>

三个页面都由东莞官网嵌入 `dgstsjzx.dg.cn` 的公开 iframe。真实参数如下：

| 公告类型 | `dirId` | `subjectId` |
|---|---|---|
| 受理情况 | `402881204e959150014e959f42f30014` | `93e889f2501d3fe8015024305bdf0efc` |
| 拟审批意见 | `402881204e959150014e95a16630002c` | `93e889f2501d3fe8015024305bdf0efc` |
| 审批决定 | `402881204e959150014e95bb85b5010f` | `93e889f2501d3fe8015024305bdf0efc` |

这些值来自官方页面当前 iframe，不是根据命名猜测所得。

### 4.2 东莞列表接口

```text
POST https://dgstsjzx.dg.cn/hbgs/zwgk/item.do
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

通用表单字段：

| 参数 | 含义 |
|---|---|
| `page` | 页码，从 1 开始 |
| `rows` | 页面传 `20`；服务端实际固定返回最多 20 条 |
| `dirId` | 上表对应目录 ID |
| `subjectId` | 上表公共 subject ID |
| `captchaId` | 第 1～3 页留空 |
| `HBTB_XH` | 受理号起始值，可空 |
| `HBTB_XH_END` | 受理号结束值，可空 |

日期筛选字段：

| 公告类型 | 开始日期 | 结束日期 |
|---|---|---|
| 受理情况 | `HBTB_SLRQ` | `HBTB_SLRQ_END` |
| 拟审批意见 | `HBTB_GSSJ` | `HBTB_GSSJ_END` |
| 审批决定 | `HBTB_GSSJ` | `HBTB_GSSJ_END` |

日期格式实测使用 `YYYY-MM-DD`。

受理情况还可传：

- `HBTB_XMMC`：项目名称
- `HBTB_JSDD`：建设地点
- `HBTB_JSDW`：建设单位

响应结构为标准 EasyUI 数据格式：

```json
{
  "total": 124596,
  "rows": [
    {
      "HBTB_XH": 20260009730,
      "HBTB_XMMC": "东莞市超强五金制品有限公司扩建项目",
      "HBTB_JSDD": "广东省东莞市东城街道基东路3号",
      "HBTB_JSDW": "东莞市超强五金制品有限公司",
      "HBTB_SLRQ": "2026-07-14 00:00:00",
      "HBTB_HPJG": "广东亿鼎环保工程有限公司",
      "HBTB_HPWJ": "{...}",
      "HBTB_LXR": "东莞市生态环境局东城分局",
      "HBTB_LXDH": "0769-22332663",
      "HBTB_TXDZ": "...",
      "HBTB_BZ": "...",
      "ID": "b83de7d..."
    }
  ]
}
```

普通 HTTP 客户端实测可直接取得数据，无需：

- Cookie
- 登录
- Token
- Authorization
- 自定义签名
- 浏览器执行 JavaScript

实现时还确认了一个请求头细节：该接口会对 `Accept: application/json` 返回 HTTP 403；使用官网兼容的 `Accept: */*` 可正常返回。响应头虽然是 `text/html;charset=UTF-8`，正文实际为 JSON，因此仍需按 JSON schema 严格校验。该行为不涉及 Cookie、Token 或签名。

`rows=5` 时服务端仍返回 20 条，因此实现不要依赖请求值改变服务端页容量，统一按 20 计算。

### 4.3 三类公告实测

2026-07-14 脱离浏览器直接 POST 的结果：

| 分类 | 总量（动态） | 第一条日期/项目 |
|---|---:|---|
| 受理情况 | 124596 | 2026-07-14，东莞市超强五金制品有限公司扩建项目 |
| 拟审批意见 | 99282 | 2026-07-14，东莞市铭瑞丰科技有限公司 |
| 审批决定 | 92406 | 2026-07-13，东莞市桥头丰硕塑胶制品厂（重新报批） |

总量较大，证明不适合无边界全量回扫；日常应采用增量日期窗口。

### 4.4 东莞分页验证码边界

这是实现时最重要的限制。

实测同一个受理列表：

- 第 1 页：HTTP 200 + JSON
- 第 2 页：HTTP 200 + JSON
- 第 3 页：HTTP 200 + JSON
- 第 4 页：HTTP 200，但正文为：

```html
<script type="text/javascript">alert('请输入验证码');</script>
```

- 第 10 页：同样返回“请输入验证码”脚本

即：

- 不能只按 HTTP 200 判断成功。
- 必须检查响应是否为 JSON。
- 命中验证码时应明确记录“需要验证码”，不能误判成空列表。
- 不应逆向、破解或自动识别验证码，也不应伪造 `captchaId`。

### 4.5 合规且可持续的增量分片

东莞官网主动提供日期范围和受理号范围筛选。应使用这些正常查询能力缩小结果集，而不是请求第 4 页。

实测日期筛选：

| 分类 | 日期范围 | 筛选后总量 |
|---|---|---:|
| 受理情况 | 2026-07-13～2026-07-14 | 41 |
| 拟审批意见 | 2026-07-13～2026-07-14 | 21 |
| 审批决定 | 2026-07-13～2026-07-14 | 15 |
| 受理情况 | 仅 2026-07-14 | 12 |

实测受理号范围：

- 受理情况 `20260009730～20260009734`：5 条
- 拟审批意见 `20260008381～20260008393`：2 条
- 审批决定 `20260007700～20260008017`：36 条

推荐算法：

1. 默认只采最近 2 天，覆盖定时任务偶发中断。
2. 对每个分类先请求第 1 页并读取 `total`。
3. 若 `total <= 60`，读取 `ceil(total / 20)` 页，最多 3 页。
4. 若 `total > 60` 且日期区间包含多天，按日期中点拆成两个区间后递归查询。
5. 若单日仍超过 60，先用 `0～99999999999` 的完整数字受理号域查询，并要求其 `total` 与未加受理号条件时完全一致；不一致说明存在空值、非数字或域外值，立即失败报警。
6. 对通过守恒检查的数字域使用官网 `HBTB_XH/HBTB_XH_END` 范围二分；每个叶子分片的唯一记录数必须等于该分片 `total`，两个子分片合并后的唯一记录数也必须等于父分片 `total`。
7. 始终不请求第 4 页，不调用验证码接口，不生成或伪造 `captchaId`。
8. 如果响应不是 JSON、出现验证码提示、抓取期间 `total` 变化或任一层数量不守恒，立即停止该分片并将任务标记失败，不能静默漏数。

这不是破解访问控制，而是使用页面本身提供的查询条件做普通增量检索，并且严格停留在无需验证码的公开结果范围内。

历史回补建议按月或按周分批运行，并持久化回补检查点；不要一次性回扫三个目录的全部十几万条记录。

### 4.6 东莞详情页

详情为公开服务端 HTML：

```text
GET https://dgstsjzx.dg.cn/hbgs/zwgk/view.do
    ?dirId=<目录ID>
    &id=<rows[n].ID>
    &subjectId=93e889f2501d3fe8015024305bdf0efc
```

实测无需登录、Cookie 或 Token，页面直接返回二维字段表格。

受理详情字段包括：

- 受理号
- 项目名称
- 建设地点
- 建设单位
- 受理日期
- 环境影响评价机构
- 环境影响评价文件
- 联系人
- 联系电话
- 通讯地址
- 备注

拟审批详情字段包括：

- 项目名称
- 建设地点
- 建设单位
- 环评机构
- 项目概况
- 主要环境影响及措施
- 公众参与情况
- 公示时间
- 联系人、电话、通讯地址
- 初步审查意见

审批决定详情字段包括：

- 受理号
- 项目名称
- 文件名称
- 审批文号
- 批复文件
- 联系人、电话、通讯地址
- 公示时间

现有 `_extract_kv_tables()` 可直接解析详情页。由于列表 JSON 已包含主要字段，详情请求主要用于：

- 保存官方 HTML 快照
- 解析附件元数据
- 补全长文本
- 作为 schema 变化时的兜底

### 4.7 东莞字段映射

#### 受理情况

| 接口字段 | `Lead` 字段/处理 |
|---|---|
| `HBTB_XMMC` | `project_name` |
| `HBTB_JSDW` | `buyer_name` |
| `HBTB_JSDD` | `buyer_address` |
| `HBTB_HPJG` | `agency_name` |
| `HBTB_SLRQ` | `publish_date` |
| `HBTB_LXDH` | `phone`，政府咨询电话 |
| `HBTB_XH` | `raw_data.acceptance_number` |
| `HBTB_HPWJ` | 环评文件元数据 |
| `ID` | `raw_data.source_record_id` |
| 固定值 | `announcement_type = 受理公告` |

#### 拟审批意见

主要映射同上，另将以下长文本保存在 `raw_data`：

- `HBTB_XMGK`：项目概况
- 主要环境影响及预防/减轻措施字段
- 公众参与字段
- 初步审批意见字段

固定：`announcement_type = 审批前公示`。

#### 审批决定

| 接口字段 | 处理 |
|---|---|
| `HBTB_XMMC` | `project_name` |
| `HBTB_SPWH` | `raw_data.approval_number` |
| `HBTB_WJMC` | `raw_data.approval_file_name` |
| `HBTB_GSSJ` | `publish_date` |
| `HBTB_PFWJ` | 批复附件元数据 |
| 固定值 | `announcement_type = 批复公告` |

审批决定自身可能不带建设单位和地址。可按同一 `HBTB_XH` 与受理/拟审批记录关联补全；匹配不到时保留空值，不能根据项目名臆造。

第一阶段实现优先使用本次窗口内同一 `HBTB_XH` 的记录；窗口内没有时，再通过受理目录的官方 `HBTB_XH/HBTB_XH_END` 精确查询（日期留空）跨日期补全建设单位、建设地点和环评机构。精确查询仍只请求第 1 页且要求数量守恒；找不到或存在歧义时保留空值，不按项目名猜测。

### 4.8 东莞附件

附件字段（如 `HBTB_HPWJ`、`HBTB_PFWJ`）是 JSON 字符串，典型内容：

```json
{
  "fileId": "a307bf5c...",
  "fileName": "某项目（公示稿）.pdf",
  "type": "zzFile"
}
```

官方下载端点：

```text
POST https://dgstsjzx.dg.cn/hbgs/zwgk/zzFileDownload.do
```

表单字段：

- `fileId`
- `fileName`
- `dirId`
- `dataId`（当前记录 `ID`）

实测：

- 正确 POST 返回 HTTP 200 和附件流。
- 把参数改成 GET 返回 403。
- 当前 `BaseScraper._download_file()` 只支持 GET，因此不能直接复用。

建议分两期：

1. 首期先把附件元数据保存在 `raw_data.source_files`，保证线索采集上线。
2. 若评审确认需要自动下载，再在 `EiaScraper` 内增加一个很小的 POST 表单下载 helper；不要为单个数据源大改整个 `BaseScraper`。

---

## 5. 推荐的代码设计

### 5.1 原则

- 不引入 Playwright/Selenium。
- 不新增第三方依赖。
- 尽量只修改 `scraper/eia.py`；日期回看天数可在 `app/config.py` 增加一个配置。
- 保留现有 `BaseScraper.run()`、任务记录、进度控制和 `save_leads()`。
- 为特殊数据源增加小型 adapter，不把所有城市强行塞进同一个 CSS 选择器模型。

### 5.2 `REGIONS` 建议结构

广州、东莞应各保留一个地区，而不是在前端显示三个重复城市。一个地区内部配置多个 feed：

```python
'guangzhou': {
    'name': '广州市',
    'level': 'city',
    'adapter': 'guangzhou',
    'feeds': [
        {'type': 'gz_acceptance_api', 'announcement_type': '受理公告'},
        {'type': 'static', 'list_url': '.../hpspqgs/index.html',
         'item_selector': 'div.conts-list', 'announcement_type': '审批前公示'},
        {'type': 'static', 'list_url': '.../hpspgg/index.html',
         'item_selector': 'div.conts-list', 'announcement_type': '批复公告'},
    ],
}
```

```python
'dongguan': {
    'name': '东莞市',
    'level': 'city',
    'adapter': 'dongguan',
    'subject_id': '93e889f2501d3fe8015024305bdf0efc',
    'feeds': [
        {'dir_id': '...', 'announcement_type': '受理公告'},
        {'dir_id': '...', 'announcement_type': '审批前公示'},
        {'dir_id': '...', 'announcement_type': '批复公告'},
    ],
}
```

### 5.3 分发逻辑

`_scrape_page()` 只做清晰分发：

- 普通城市：继续走当前静态 HTML 逻辑。
- 广州：
  - 调用受理 JSON API。
  - 调用审批前和审批公告两个静态 feed。
  - 合并当页结果。
- 东莞：
  - 第一次逻辑调用内按最近日期窗口抓取三个 feed。
  - 内部按 `total` 做日期/受理号分片并读取每个分片最多 3 页。
  - 后续逻辑页返回空列表，避免 `BaseScraper.run()` 再请求第 4 页。

东莞这部分可做成一个私有方法，不需要修改全局主流程：

```text
_scrape_dongguan_window(start_date, end_date)
  -> 对三个 feed 调用 _fetch_dongguan_feed(...)
  -> total <= 60：抓 1～3 页
  -> total > 60：拆日期/受理号范围递归
  -> 合并并按 (dirId, ID) 去重
```

### 5.4 POST helper

`BaseScraper.fetch()` 仍只负责 GET。参考项目中 `GdgpoScraper._post_json()` 的现有做法，已在 `EiaScraper` 内增加：

- `_post_json()`：广州详情
- `_post_form()`：东莞列表

两者都应复用：

- `self.session`
- 随机 User-Agent
- 当前 1～2 秒延迟
- 超时和日志

响应校验必须比“HTTP 200”更严格：

- 广州：`code == 0` 且 `data` 类型正确。
- 东莞：`Content-Type/正文` 确实为 JSON，且有 `total`、`rows`。
- 若正文出现“请输入验证码”，返回明确的受控错误，不当成空数据。

另外，`BaseScraper.fetch()` 已增加向后兼容的 `return_error_response` 可选参数，仅供 EIA 静态列表区分 HTTP 404 与网络/服务错误。采集主循环会累计失败单元、继续处理其他地区，并在结束时把任务标记为“失败”。

### 5.5 去重策略

不建议把东莞 `HBTB_XH` 直接写入当前全局 `bidding_number`，原因是同一项目在“受理、拟审批、审批决定”阶段可能共用受理号，而 `BaseScraper.save_leads()` 会按该字段跨公告类型直接跳过。

首期建议保持现有环评采集的“项目级线索”语义：

- `HBTB_XH` 存 `raw_data.acceptance_number`。
- 继续按项目名称 + 建设单位去重。
- 后续阶段若已有同项目线索，先沿用现有跳过行为。

如果业务希望保留完整阶段流转，应另行评审“一个项目多条阶段记录”或“阶段历史子表”，不要在本次数据源接入中顺便扩大模型范围。

---

## 6. 为什么不采用浏览器自动化

Playwright 能渲染页面，但不是这里的最优生产方案：

- 两站核心数据都能通过公开 HTTP 接口或静态 HTML 获取。
- 浏览器运行时、二进制体积、启动失败和页面改版风险更高。
- 定时任务同时跑多个城市时资源开销明显更大。
- 浏览器自动填写/识别验证码会触碰站点明确控制，不应实施。
- 当前项目已经有成熟的 `httpx` 会话、重试、限速、快照和附件逻辑，直接适配成本最低。

因此浏览器只保留作诊断工具，不进入运行依赖。

---

## 7. 风险与保护措施

### 7.1 广州新系统使用 HTTP IP 地址

当前入口是 `http://112.94.69.56:8066`，不是稳定的 HTTPS 域名，存在：

- IP 或端口迁移
- 服务证书/域名升级
- 接口字段调整

保护措施：

- 把基地址集中为常量，不散落在解析代码中。
- 每次验证 `code/data/list/total` schema。
- 失败时日志明确标记“广州受理 API schema/入口失效”。
- 保留广州市生态环境局官方迁移页作为人工核验入口。

### 7.2 东莞目录 ID 是不透明标识

`dirId`/`subjectId` 可能随系统迁移变化。

保护措施：

- 集中配置三个 ID。
- 在维护检查中对比官方外层页面 iframe 地址。
- 不需要每次运行动态解析 iframe，避免无必要复杂度；接口失败时再重新发现即可。

### 7.3 验证码和限流

- 东莞：绝不请求第 4 页；只用官方筛选分片。
- 广州：不自动下载受验证码和 30 次/IP 上限保护的受理附件。
- 保持项目已有 1～2 秒请求间隔。
- 历史回补限速、分批、有检查点，不做高并发。

### 7.4 电话字段语义

广州和东莞详情中的联系电话均为生态环境主管部门/属地分局的公众咨询电话，不是建设单位联系人电话。

继续沿用当前模块顶部说明：

- 可写入 `Lead.phone` 供核实项目真实性。
- 不得把政府联系人写成建设单位联系人。
- 业务跟进仍需通过合法企业信息渠道查找建设单位联系方式。

### 7.5 审批决定字段不完整

东莞审批决定可能只公开项目名、审批文号和批复文件。应：

- 优先按受理号关联此前阶段补全。
- 关联失败则保留空值。
- 不按相似名称猜建设单位或地址。

---

## 8. 建议实施顺序

### 第一阶段：上线核心线索（已完成）

1. 广州接入受理 JSON API。
2. 广州接入两个静态栏目：审批前公示、审批公告。
3. 东莞接入三个公开目录的列表和详情。
4. 东莞采用最近 2 天增量窗口和官方筛选分片。
5. 固定公告类型，不再只依赖标题分类。
6. 保存 source URL、源记录 ID、受理号和源附件元数据。
7. 广州受理附件、东莞 POST 附件均暂不自动下载。
8. 增加解析 fixture 和 smoke test。

### 第二阶段：可选增强

1. 经评审后增加东莞 POST 附件下载。
2. 增加可指定日期区间的历史回补入口及检查点。
3. 若业务需要，设计项目阶段历史，而不是生成重复 Lead。
4. 对广州 2026-03-02 以前的旧静态受理栏目做一次性历史补采。

---

## 9. 验收标准

第一阶段实现按以下标准验收：

1. `region:guangzhou` 能采到：
   - 当日/最新受理记录；
   - 最新审批前公示；
   - 最新审批公告。
2. 广州受理记录至少正确映射：项目名称、建设单位、建设地点、环评单位、发布日期、官方详情地址。
3. `region:dongguan` 能采到三个阶段的最新记录，并正确映射项目、单位、地点、日期和公告类型。
4. 东莞列表请求不带 Cookie、Token、签名，仍返回 JSON。
5. 代码永不请求东莞第 4 页；任何验证码响应都被识别为受控失败并记录日志。
6. 日期/受理号分片合并后按 `(dirId, ID)` 去重，无漏页、无重复。
7. 广州受理定时采集不会触发附件验证码或消耗 30 次/IP 下载额度。
8. `source_url` 可由人工浏览器打开核验。
9. 两市政府联系电话不会被标记为建设单位联系人。
10. 现有广东省、江门及其他已接入城市采集不受影响。

---

## 10. Review 决策与实施边界

本次第一阶段已按以下方案实施：

- **批准使用 `httpx` 直连公开接口/静态 HTML。**
- **不批准引入 Playwright 作为生产依赖。**
- **不批准自动绕过广州附件验证码或东莞第 4 页验证码。**
- **批准用官方日期/受理号筛选做东莞增量分片。**
- **本次以核心线索字段为优先，附件自动下载延后。**
- **首期保持项目级去重语义，阶段历史另行评审。**

该方案已经通过真实接口请求验证，可在当前架构内落地，并且比浏览器自动化更轻、更稳定、更符合现有项目的实现方式。
