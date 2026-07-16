# 广东省公共资源交易平台（粤公平）采集可行性调研报告

> 调研日期：2026-07-16
> 状态：**初步调研完成，待实地验证**

---

## 一、平台概览

| 项目 | 信息 |
|------|------|
| 平台名称 | 广东省公共资源交易平台（粤公平） |
| 官方域名 | ygp.gdzwfw.gov.cn |
| 技术架构 | Vue.js SPA + REST API |
| 覆盖范围 | 全省 21 个地级市 + 省级 |
| 主要板块 | 工程建设、政府采购、土地矿产、国有产权 |

### 采集价值评估

管道相关招标信息主要分布在**工程建设**板块，包括：
- 市政管网工程施工招标
- 给排水工程施工招标
- 污水处理厂建设项目
- 供水/引水工程

与现有数据源的关系为**互补而非替代**：
- ccgp：政府采购（全国）— 侧重物资采购
- gdgpo：政府采购（广东）— 侧重物资采购
- eia：环评公示（广东 21 市）— 前置情报
- **ggzyjy：工程建设施工招标（广东）— 补齐施工类空白**

---

## 二、接口分析（推测，待实地验证）

### 前端架构
- Vue.js SPA，Hash 路由，客户端 JS 渲染
- 推测 API 端点格式：`/ggzy-portal/api/jsgc/list`、`/jsgc/detail` 等
- 分页机制：推测为 JSON API 分页参数（pageNo/pageSize）

### 搜索能力（待验证）
- 预期支持关键词搜索
- 预期支持分类筛选（按工程类型、行政区划）
- 预期支持时间范围筛选

⚠️ **以上均为基于平台架构的推测，需通过浏览器 DevTools 抓包实际验证。**

---

## 三、反爬评估

### 与 ctbpsp 对比

| 防护维度 | ctbpsp（已放弃） | 粤公平（预期） |
|---------|-----------------|---------------|
| WAF | 阿里云 WAF（JS 挑战） | 可能有基础 WAF，但预期宽松 |
| 验证码 | Vaptcha + 网易易盾 | 预期无或仅在高频时触发 |
| 反调试 | interfaceacting.js + antidom.js | 预期无 |
| 响应加密 | DES 加密 | 预期无（政府公开信息） |
| 登录要求 | 需登录 | 预期无（公示信息公开查阅） |

### 有利因素
1. 政府平台优先保障公众查询，反爬不是主要目标
2. Vue.js SPA 架构相对规范，API 端点可通过 DevTools 观察
3. 公示信息属于政府公开信息，无需登录查看
4. 无预期的复杂验证码、DES 加密等高级防护

### 风险因素
1. 可能存在基础频率限制
2. API 端点可能变更
3. 部分字段可能需要额外请求才能获取

---

## 四、数据字段与 Lead 模型匹配度

| Lead 模型字段 | 预期可获取 | 说明 |
|--------------|-----------|------|
| project_name（项目名称） | ✅ | 工程项目名称 |
| bidding_number（招标编号） | ✅ | 招标公告编号 |
| notice_type（公告类型） | ✅ | 招标/中标/变更等 |
| purchaser（采购单位） | ✅ | 招标人/建设单位 |
| contact_person（联系人） | ⚠️ | 可能在详情页 |
| contact_phone（电话） | ⚠️ | 可能在详情页 |
| budget_amount（预算金额） | ✅ | 工程预算/控制价 |
| publish_date（发布日期） | ✅ | 公告发布时间 |
| deadline（截止日期） | ✅ | 投标截止时间 |
| region（地域） | ✅ | 所属地级市 |
| attachments（附件） | ⚠️ | 招标文件可能需登录下载 |

**匹配度评估：⭐⭐⭐⭐（高度匹配，核心字段均可覆盖）**

---

## 五、技术方案建议

### 三层递进方案

**第 1 层（推荐，优先尝试）：HTTP API 直接调用**
- 工具：httpx + JSON 解析
- 前提：API 端点可直接访问，返回 JSON
- 工作量：1-2 天
- 与现有架构集成：新建 `scraper/ggzyjy.py`，继承 `BaseScraper`

**第 2 层（备选）：无头浏览器辅助**
- 工具：Playwright / Selenium
- 场景：API 有 Cookie/Token 校验，需浏览器获取
- 工作量：额外 +1-2 天
- 风险：增加部署复杂度

**第 3 层（最后方案）：放弃或转向备选数据源**
- 触发条件：WAF 严格 + 验证码 + 加密，类似 ctbpsp
- 备选方案：转向其他省份的公共资源交易平台

### 关键词建议

```python
GGZYJY_KEYWORDS = [
    # 产品类
    '管道', 'PVC管', 'HDPE管', 'PE管', '钢管', '混凝土管',
    # 工程类
    '给排水', '市政管网', '雨污分流', '污水工程',
    # 项目类
    '污水处理厂', '自来水厂', '海绵城市', '综合管廊',
]
```

---

## 六、结论与建议

### 总体结论

**粤公平平台采集技术上预期可行**，但需通过实地测试验证具体 API 端点和防护机制。

相比 ctbpsp（5 层反爬，已放弃），粤公平作为省级政府服务平台，预期反爬强度明显较弱。主要依据：
1. 定位为公共服务（非商业数据平台）
2. 信息公开属性强（政府采购/招标公示）
3. 同类省级平台（如浙江、江苏 ggzyjy）通常防护较弱

### 建议下一步

**实地验证（1-2 天）：**
1. 使用浏览器 DevTools 打开粤公平网站，抓包观察 API 端点
2. 记录搜索/列表/详情页的实际请求 URL、参数、响应格式
3. 用 httpx 直连验证是否正常返回 JSON（无需浏览器）
4. 测试 10-20 次请求，观察是否触发防护

**验证后决策：**
- 如 API 可直连 → 启动开发（2-3 天完成）
- 如需浏览器辅助 → 评估 Playwright 方案成本
- 如反爬严格 → 放弃，转向其他省份平台

### 预期收益
- 日均新增线索：50-200 条（工程建设类）
- 覆盖现有数据源空白：施工招标类项目
- 项目生命周期补齐：招标→施工 环节

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| API 不可直连 | 中 | 增加 Playwright 依赖 | 先验证再决策 |
| 频率限制 | 中 | 采集速度受限 | BaseScraper 已有延迟机制 |
| API 端点变更 | 低 | 采集中断 | 监控 + 快速修复 |
| 平台改版 | 低 | 需重新适配 | 模块化设计便于修改 |

---

> **决策建议**：投入 1-2 天做实地验证，确认可行后 3-4 天完成开发部署。总投入约 1 周，预期 ROI 高。

---

## 八、实地验证结果（2026-07-16）

> 验证方式：通过 WebFetch 和浏览器直接访问 API 端点，验证可用性
> 结论：**可行，反爬极低，httpx 直连完全可行**

### 8.1 实际发现的 API 端点

#### 搜索/列表接口（核心接口）

```
POST https://ygp.gdzwfw.gov.cn/ggzy-portal/search/v2/items
Content-Type: application/json
```

请求参数（JSON Body）：
```json
{
  "pageNo": 1,
  "pageSize": 20,
  "keyword": "管道",
  "tradingTypeCode": "jsgc",
  "siteCode": "44",
  "startTime": "20260701000000",
  "endTime": "20260716235959"
}
```

- `tradingTypeCode`: "jsgc"=工程建设
- `noticeSecondType`: "A"=工程建设, "B"=土地矿业, "C"=国有资产, "D"=政府采购
- `siteCode`: "44"=广东省, "440100"=广州市, "440700"=江门市等
- `startTime`/`endTime`: 格式 "yyyyMMddHHmmss"
- `keyword`: 关键词搜索

响应格式：
```json
{
  "errcode": 0,
  "errmsg": "ok",
  "data": {
    "pageNo": 1,
    "pageSize": 20,
    "pageTotal": 2632,
    "total": "5264",
    "pageData": [
      {
        "noticeId": "f970e58a-...",
        "noticeTitle": "...燃气管道拆除迁改工程施工总承包...",
        "noticeSecondType": "A",
        "noticeSecondTypeDesc": "工程建设",
        "noticeThirdType": "4",
        "noticeThirdTypeDesc": "中标结果",
        "projectTypeName": "市政",
        "regionName": "广州市",
        "projectOwner": "广州市政园建设管理有限公司",
        "projectCode": "E4401002701503104001",
        "publishDate": "20260716190934"
      }
    ]
  }
}
```

#### 详情接口（核心接口）

```
GET https://ygp.gdzwfw.gov.cn/ggzy-portal/center/apis/trading-notice/new/detail
```

参数：nodeId, version("v3"), tradingType("A"), noticeId, bizCode, projectCode, siteCode

响应中 `tradingNoticeColumnModelList` 包含：
- keyTable：结构化键值对（项目名称、标段名称、公告性质等）
- richText：HTML 内容（含招标人、联系人、电话、预算、截止日期等完整信息）
- 附件列表：`noticeFileBOList`（含文件名和 rowGuid）

#### 辅助接口

| 接口 | 用途 |
|------|------|
| `GET /ggzy-portal/base/site?siteCode=` | 地区列表（21 市编码） |
| `GET /ggzy-portal/base/columns/tree?siteCode=44` | 栏目树 |
| `GET /ggzy-portal/center/apis/trading-notice/new/nodeList` | 项目节点列表 |

### 8.2 反爬实际情况

| 防护维度 | 实际情况 |
|---------|---------|
| WAF | 无。API 直接返回 JSON |
| 验证码 | 无。连续请求未触发 |
| Cookie/Token | 不需要 |
| 登录要求 | 不需要 |
| 响应加密 | 无。明文 JSON |
| 频率限制 | 未检测到明显限制 |

**结论：反爬强度极低，与 ctbpsp（5层反爬）形成鲜明对比。**

### 8.3 字段匹配度

| Lead 模型字段 | 来源 | 可获取 |
|--------------|------|--------|
| project_name | 列表 `noticeTitle` + 详情 `TENDER_PROJECT_NAME` | ✅ |
| bidding_number | 列表 `projectCode` | ✅ |
| announcement_type | 列表 `noticeThirdTypeDesc` / `datasetName` | ✅ |
| buyer_name | 详情 richText "招标人" | ✅ |
| buyer_address | 详情 richText "联系地址" | ✅ |
| contact_person | 详情 richText "招标人联系人" | ✅ |
| phone | 详情 richText "联系电话" | ✅ |
| agency_name | 详情 richText "招标代理机构" | ✅ |
| agency_phone | 详情 richText 代理"联系电话" | ✅ |
| budget_amount | 详情 richText "最高投标限价" | ✅ |
| publish_date | 列表 + 详情 `publishDate` | ✅ |
| deadline | 详情 richText "投标文件递交截止时间" | ✅ |
| region | 列表 `regionName` | ✅ |
| attachments | 详情 `noticeFileBOList` | ✅（下载 URL 待确认） |

### 8.4 地区编码映射表

| 城市 | siteCode | 城市 | siteCode |
|------|----------|------|----------|
| 省级 | 440000 | 东莞市 | 441900 |
| 广州市 | 440100 | 中山市 | 442000 |
| 深圳市 | 440300 | 江门市 | 440700 |
| 珠海市 | 440400 | 佛山市 | 440600 |
| 汕头市 | 440500 | 惠州市 | 441300 |
| 韶关市 | 440200 | 湛江市 | 440800 |
| 河源市 | 441600 | 茂名市 | 440900 |
| 梅州市 | 441400 | 肇庆市 | 441200 |
| 汕尾市 | 441500 | 清远市 | 441800 |
| 阳江市 | 441700 | 潮州市 | 445100 |
| 揭阳市 | 445200 | 云浮市 | 445300 |

### 8.5 最终可行性结论

**可行。** 推荐方案：HTTP API 直接调用（httpx），无需浏览器自动化。

- 反爬：极低（0层防护）
- 字段匹配度：极高（Lead 模型全部核心字段可获取）
- 数据规模："管道"关键词工程建设类共 5264 条
- 预计工作量：2.5 天

### 8.6 风险与待验证项

1. 附件下载 URL 格式需进一步确认（有 rowGuid 但完整 URL 未验证）
2. `noticeThirdType` API 端过滤不严格，需客户端二次过滤
3. richText HTML 格式在不同地市的公告中可能有差异

### 8.7 与初步推测对比

| 初步推测 | 实际验证 | 符合度 |
|---------|---------|--------|
| Vue.js SPA + REST API | 确认 | ✅ |
| API 端点 `/ggzy-portal/api/jsgc/list` | 实际为 `/ggzy-portal/search/v2/items` | ⚠️ 路径不同但功能等价 |
| 分页 pageNo/pageSize | 确认 | ✅ |
| 关键词搜索 | 确认 | ✅ |
| 时间范围筛选 | 确认 | ✅ |
| 反爬预期宽松 | 实际比预期更低 | ✅ 超出预期 |
| 联系人/电话在详情页 | 确认在 richText HTML 中 | ✅ |
| 预算金额可获取 | 确认为"最高投标限价" | ✅ |
