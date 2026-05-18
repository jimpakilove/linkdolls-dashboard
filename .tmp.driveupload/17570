# LinkDolls 数据看板 — 项目说明

> 本文档面向开发者/Agent，帮助快速理解项目架构和数据处理逻辑。

---

## 1. 项目定位

LinkDolls Shopify 店铺的内部 SEO/运营数据看板，核心功能：
- 追踪每个 Collection 分类页的 **GSC（搜索控制台）** + **GA4（分析）** 数据
- 对比 Q1/Q2/Q3/Q4 的 **流量目标** 和 **收入目标**
- 按产品首字母做**类别横向对比**（Ass/Torso/Full Doll/Head 等）

---

## 2. 技术架构

```
Shopify 订单 CSV
    │
    ▼
GSC/GA4 周数据 CSV ──► aggregate_detail.py ──► dashboard_detail.json
    │                                              │
    │                                              ├──► dashboard.html (主看板)
    │                                              ├──► dashboard_collection.html (分类页看板)
    │                                              └──► category_revenue.json (类别横向对比)
    │
python3 server.py (port 8765)
```

**纯静态，无框架**：Python http.server + 单文件 HTML/Chart.js SPA，无构建步骤。

---

## 3. 目录结构

```
landing-page-data/
├── {category-slug}/              # 每个 Collection 分类页一个目录
│   └── w{NN}_{YYYY-MM-DD}/      # 每周一个子目录
│       ├── 网页.csv              # GSC: 点击、曝光、排名、CTR
│       ├── 查询数.csv            # GSC: 搜索关键词
│       ├── 设备.csv              # GSC: 设备分布
│       ├── 国家_地区.csv          # GSC: 国家分布
│       ├── 购买历程_设备类别.csv   # GA4: 转化漏斗
│       ├── 页面点击数.csv         # GA4: 页面点击事件
│       └── 电子商务购买_商品名称*.csv  # GA4: 商品购买
├── pageviews/                    # GA4 页面浏览数（按周全局）
├── config/
│   └── target-2026.csv          # 季度流量/收入目标配置
├── orders/                       # Shopify 订单明细导出
│   └── 订单明细表导出YYYY-MM-DD.csv
├── aggregate_detail.py           # ETL 聚合脚本
├── server.py                     # http.server 静态服务
├── dashboard_detail.json         # 主数据源（~4MB）
├── category_revenue.json         # 类别横向对比数据源
├── dashboard.html                # 主看板（含嵌入数据）
├── dashboard_collection.html     # 分类页数据看板
└── dashboard_category.html       # 类别横向对比页
```

---

## 4. 核心脚本：`aggregate_detail.py`

### 4.1 订单加载（`load_orders_all`）

**数据源**：`orders/订单明细表导出*.csv`

**去重策略**（关键！）：
- Shopify 导出时，同一订单-产品组合可能因**多个 Order tag** 而出现多行
- 按 `(订单名称, 产品标题)` 去重
- **优先保留 Order tag 为 `/collections/` 的行**（对分类页收入归因至关重要）
- 过滤 `Shipping Protection` 等非产品项

```
原始: 1891 行
去重后: 703 行
丢失的 /collections/ 匹配从 368 → 351（仅损失 17 行）
```

### 4.2 收入归因 — 两套逻辑

⚠️ **这是最容易搞混的地方，两套逻辑服务不同看板：**

#### A. `calculate_revenue_by_category()` — 分类页数据看板用

**归因方式**：按 **Order tag** 精确匹配 `/collections/{category}`

```
订单行 → 读取 Order tag → 标准化（去 /en-ca/ 等语言前缀）
        → 精确匹配 /collections/{category} → 成功则计入该分类
        → 匹配失败则丢弃（不归入任何分类）
```

**局限**：大量订单的 tag 是 `xcottonsp`、`260430`、`加急快递` 等非 `/collections/` 格式，这些收入不会被任何分类页统计。

**输出格式**：按季度拆分（Q1/Q2/Q3/Q4），含 `orders`、`totalSales`、`products`、`monthlySales`。

#### B. `calculate_category_weekly_revenue()` — 类别横向对比用

**归因方式**：按 **Product title 首字母** 归类

```
订单行 → 读取 Product title → 正则匹配开头字母+数字（如 "F6209..." → "f"）
        → 按首字母映射到类别（f→Full Doll, a→Ass, t→Torso...）
        → 按订单日期归入对应周 → 汇总净销售额
```

**映射表**：
| 首字母 | 类别 |
|--------|------|
| a | Ass 臀部 |
| b | Boob 胸部 |
| d | Dildo 假阳具 |
| f | Full Doll 完整娃 |
| h | Head 头部 |
| l | Legs 腿部 |
| p | Pussy 内部 |
| t | Torso 躯干 |
| v | Vajankle 足踝 |
| other | Other 其他 |

**注意**：首字母分类是**粗糙聚合**，多个 Collection 页共享同一首字母。例如 `sex-doll-torso` 和 `sex-doll-torso-dildo` 都映射到 `t`。

### 4.3 日期标准化（`normalize_date`）

支持格式：`2026/5/4`、`2026-05-04`、`2026/05/04` → 统一为 `2026-05-04`

⚠️ 月度汇总必须使用标准化后的日期，否则月份解析会出错（如 `2026/1/12` 直接取 `1/1` 得到 `1` 而非 `01`）。

### 4.4 输出文件

| 文件 | 用途 | 消费者 |
|------|------|--------|
| `dashboard_detail.json` | 每个分类每周的完整数据（GSC + GA4 + 收入） | `dashboard.html`, `dashboard_collection.html` |
| `category_revenue.json` | 按首字母+周汇总的收入数据 | `dashboard.html` 的"类别横向对比" |

---

## 5. 前端看板

### 5.1 `dashboard.html` — 主看板

- **嵌入数据**：`window.__CAT_DATA__` 包含所有产品级数据（Top 50 产品列表）
- **类别横向对比**：启动时 `fetch('category_revenue.json')` 加载收入数据，覆盖嵌入数据中的零值
- **刷新方式**：访问 `http://localhost:8765/api/refresh` 触发后端执行 `aggregate_detail.py`

### 5.2 `dashboard_collection.html` — 分类页数据看板

- **动态加载**：`fetch('dashboard_detail.json')`
- **分类筛选器**：从 JSON 的 `config` 字段按负责人分组
- **收入展示**：读取 `revenue.{quarter}.totalSales`

### 5.3 `dashboard_category.html` — 类别横向对比（独立页面）

- 直接读取 `category_revenue.json`
- 展示按首字母分类的周度收入走势

---

## 6. 已知陷阱 & 注意事项

### 6.1 收入数据两套逻辑不要混用

| 看板 | 归因方式 | 数据源 | 适用场景 |
|------|---------|--------|---------|
| 分类页数据看板 | Order tag → `/collections/{category}` | `dashboard_detail.json` | 看具体 Collection 页表现 |
| 类别横向对比 | Product title 首字母 | `category_revenue.json` | 看产品大类整体表现 |

**不要改 `calculate_revenue_by_category` 为首字母归因**，否则分类页看板会显示所有映射到同一首字母的 Collection 共享收入，失去按页归因的意义。

### 6.2 去重策略影响分类页收入

如果去重时不优先保留 `/collections/` tag 的行，`calculate_revenue_by_category` 会大幅丢失数据（从 351 行降到 160 行）。

### 6.3 `full-doll` 等父级 Collection 收入天然偏低

顾客通常从子分类（如 `/collections/anime-sex-doll`）下单，Order tag 记录的是子分类而非父级 `/collections/full-doll`。这是 Shopify 的正常行为，不是 bug。

### 6.4 周标签对齐

`category_revenue.json` 使用 `W1`~`W52`（全年），而嵌入数据 `__CAT_DATA__` 可能只包含部分周（如 `W10`~`W19`）。前端合并时需要做周标签映射。

### 6.5 缓存问题

`dashboard.html` 和 `dashboard_collection.html` 都内嵌/动态加载 JSON，浏览器可能缓存旧数据。数据更新后务必**强制刷新**（Mac: `Cmd + Shift + R`）。

---

## 7. 启动命令

```bash
cd ~/Desktop/linkdolls\ dashboard/landing-page-data
python3 server.py
```

访问：
- 主看板：`http://localhost:8765/dashboard.html`
- 分类页看板：`http://localhost:8765/dashboard_collection.html`
- 刷新数据：`http://localhost:8765/api/refresh`

---

## 8. 维护 checklist

- [ ] 每周更新 GSC/GA4 CSV 到对应 `{category}/w{NN}_{date}/` 目录
- [ ] 每月更新 Shopify 订单导出到 `orders/`
- [ ] 数据更新后执行 `python3 aggregate_detail.py` 或访问 `/api/refresh`
- [ ] 强制刷新浏览器清除缓存
- [ ] 检查 `category_revenue.json` 周标签是否与嵌入数据对齐
