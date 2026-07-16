# ctbpsp.com 真实 API 调研与采集可行性分析

> 调研日期：2026-07-15
> 调研人：自动化分析
> 结论：**不可行（除非引入浏览器自动化 + 打码平台）**

---

## 一、网站概况

| 项目 | 详情 |
|------|------|
| 网站名称 | 全国招标公告公示搜索引擎 - 中国招标投标公共服务平台 |
| 域名 | ctbpsp.com（原 www.ctbpsp.com 已 301 到 ctbpsp.com） |
| 技术栈 | Vue.js SPA + Element UI + iView |
| 路由方式 | Hash 路由（`#/search`） |
| 数据加载 | 客户端 JS 通过 XHR 调用后端 API |

---

## 二、真实 API 接口（通过 JS 逆向分析得出）

### 2.1 搜索接口

```
POST https://ctbpsp.com/cutominfoapi/searchkeyword?<url_encoded_keyword>
Content-Type: application/json
```

**请求体（JSON）：**
```json
{
  "keyword": "消防管网",
  "uid": 0,
  "PageSize": 20,
  "CurrentPage": 1,
  "searchType": 0,
  "bulletinType": ""
}
```

**请求头（关键反爬）：**
- 第 1 页需要 `Necaptcha-Validate`（网易易盾验证码 token）
- 后续页需要 `V-Token`、`V-Knock`、`V-Dfu`（Vaptcha 人机验证结果）

### 2.2 其他接口

| 接口 | 用途 |
|------|------|
| `POST /cutominfoapi/searchkeyword?` | 搜索（关键词匹配标题） |
| `POST /cutominfoapi/searchkeyword/updateitem` | 搜索（关键词匹配内容） |
| `GET /cutominfoapi/recommand/{type}/{pagesize}/{currentpage}` | 首页推荐列表 |
| `GET /cutominfoapi/bulletin/{bulletinId}` | 公告详情 |
| `GET /cutominfoapi/bulletinuuid/{uuid}` | 按 UUID 查详情 |
| `GET /cutominfoapi/getBulletinAttachmentUrl?bulletinId=` | 附件下载 |

### 2.3 响应加密

API 返回的数据是 **DES 加密**的，密钥为 `1qaz@wsx3e`（ECB 模式，PKCS7 填充）。解密代码在 app.js 中：

```javascript
function X(e) {
    var t = CryptoJS.enc.Utf8.parse("1qaz@wsx3e"),
        i = CryptoJS.DES.decrypt({
            ciphertext: CryptoJS.enc.Base64.parse(e)
        }, t, {
            mode: CryptoJS.mode.ECB,
            padding: CryptoJS.pad.Pkcs7
        });
    return i.toString(CryptoJS.enc.Utf8);
}
```

---

## 三、反爬机制（5 层防护）

### 第 1 层：阿里云 WAF（Web 应用防火墙）

- **cookie**：`acw_tc`（阿里云 WAF 的 session cookie）
- **JS 挑战**：首次访问 API 返回的不是 JSON，而是一个高度混淆的 JS 挑战页面（约 200KB 混淆代码），需要浏览器执行 JS 后才能拿到通行 cookie
- **实测**：直接 curl 带 cookie 也过不了，返回的仍然是 JS 挑战页面

### 第 2 层：Vaptcha 人机验证

- 配置：`vid: "id_aee90e9132f52aa"`，`container: "#vaptcha-container"`
- 搜索第 1 页需要完成滑块/点击验证
- 验证通过后获得 `V-Token`、`V-Knock`、`V-Dfu` 三个 header 值
- 后续页使用这三个 header 即可

### 第 3 层：网易易盾（NetEase Shield）

- 脚本：`cstaticdun.126.net/load.min.js`
- 作为 Vaptcha 的替代方案（`Necaptcha-Validate` header）
- 用于第 1 页搜索请求

### 第 4 层：阿里系前端反调试

- `g.alicdn.com/frontend-lib/.../interfaceacting.js` — 接口行为检测
- `g.alicdn.com/frontend-lib/.../antidom.js` — 反 DOM 操作检测

### 第 5 层：数据加密

- 所有 API 响应均为 DES 加密的 Base64 字符串
- 密钥硬编码在前端 JS 中（`1qaz@wsx3e`），这个倒不难解

---

## 四、实际测试结果

### 4.1 直接 API 调用（无验证码）

```
curl -X POST "https://ctbpsp.com/cutominfoapi/searchkeyword?消防管网" \
  -H "Content-Type: application/json" \
  -d '{"keyword":"消防管网","uid":0,"PageSize":20,"CurrentPage":1,"searchType":0,"bulletinType":""}'
```

**结果**：返回 WAF JS 挑战页面（HTML），无法获取数据。

### 4.2 带 WAF cookie 调用

```
curl -b "acw_tc=xxx" -X POST "..." ...
```

**结果**：仍然返回 WAF JS 挑战页面。WAF cookie 需要通过 JS 执行才能正确生成。

### 4.3 替代域名尝试

| 域名 | 结果 |
|------|------|
| `custominfo.cebpubservice.com/cutominfoapi/...` | 404 |
| `bulletin.cebpubservice.com/cutominfoapi/...` | 404 |
| `www.ctbpsp.com` | 301 到 ctbpsp.com |

---

## 五、可行性评估

### 方案 A：纯 HTTP 请求（当前方案）

**可行性：❌ 不可行**

WAF JS 挑战 + Vaptcha/网易易盾双重验证，纯 HTTP 库无法通过。

### 方案 B：Headless Browser（Playwright/Puppeteer/Selenium）

**可行性：⚠️ 理论可行，成本较高**

需要：
1. 启动 headless 浏览器，加载 SPA 页面
2. 等待 WAF JS 挑战完成（~2-5 秒）
3. 触发搜索，等待 Vaptcha 验证码弹出
4. 对接打码平台（如 2captcha、超级鹰）解决 Vaptcha
5. 拿到 V-Token/V-Knock/V-Dfu 后，后续页可直接调 API
6. 对 API 返回的加密数据用 DES 解密

**成本估算**（按 30 个关键词采集）：
- 打码平台：每个关键词约需 1 次验证 ≈ 0.5-2 元/次
- 浏览器资源：每个 headless 浏览器约 300-500MB 内存
- 采集速度：每次请求需 3-5 秒延迟，单个关键词 5 页约 25 秒
- 总计约 30 关键词 × 0.5 元 ≈ 15-60 元/轮

### 方案 C：对接第三方数据服务

**可行性：✅ 最可行**

中国招标投标公共服务平台（ctbpsp.com）是国家级平台，数据同时发布在多个渠道：
- 各省市公共资源交易中心网站（通常没有验证码）
- 第三方招标数据聚合商（如招标雷达、千里马等）
- 可以购买 API 服务，按月/按量付费

---

## 六、建议

### 短期（推荐）

**放弃 ctbpsp.com 的直接采集**，改用以下替代数据源：

1. **各省市公共资源交易中心**：数据同源，且通常无反爬或反爬较弱
2. **现有的 eia（环评公示）采集器**：已验证可用，继续优化
3. **其他已接入的采集源**（如果项目中有其他可用源）

### 中期（如果确实需要 ctbpsp 数据）

采用 **Playwright + 打码平台** 方案：
- 使用 Playwright 启动 headless Chromium
- 先访问首页完成 WAF 挑战
- 模拟真实用户搜索行为
- 对接 2captcha 或 CapSolver 解决 Vaptcha
- 复用 V-Token 完成后续翻页

### 长期

如果招标数据是核心需求，建议采购第三方招标数据 API 服务，省去采集和维护成本。

---

## 七、关键代码位置

| 文件 | 说明 |
|------|------|
| `scraper/ctbpsp/api.py` | 当前 API 封装（URL 全错，需重写） |
| `scraper/ctbpsp/parser.py` | 响应解析器（字段路径需验证） |
| `scraper/ctbpsp/__init__.py` | 采集器主类 |
| `scraper/ctbpsp/utils.py` | 工具函数 |

当前代码中所有 `⚠️` 标记的预判值均已被本次调研验证为错误，需要根据本报告中的真实 API 信息重写。

---

## 八、附录：WAF 挑战样本

首次不带有效 cookie 访问 API 时，返回的 HTML 页面包含：
- 约 200KB 混淆后的 JavaScript 代码
- 一个隐藏的 `<textarea id="renderData">` 包含 WAF token：
  ```json
  {"_waf_bd8ce2ce37":"U2ns52ozMjDjI9DQ/GJnQ+9gmgB3w8SBZogSCtwQZV0="}
  ```
- 该 JS 代码会执行浏览器指纹检测、localStorage 读写、cookie 设置等操作，最终生成有效的 `acw_tc` cookie 后才能访问真实 API