# LinkDolls 详情页（PDP）数据看板需求梳理

> 基于已有分类页看板扩展，覆盖全站产品详情页。版本：v0.1 草稿

---

## 1. 目标与定位

在已有 collection 级看板之外，新增一套产品详情页（`/products/{handle}`）级别的数据看板，用于：

- 以 PDP 为最小颗粒度诊断 SEO/流量/转化问题
- 支持"品牌 → 分类 → 单品"的层级分析
- 对接运营对单品级增长的管理需求

定位上与分类页看板**互补**而非替代：分类页看板回答"哪个赛道在涨/在退"，PDP 看板回答"这个赛道里哪个单品在扛量、哪个拖后腿"。

---

## 2. 覆盖范围

- **全量 PDP**：所有 `/products/*` 路径，不做白名单筛选
- 新上/下架 PDP 自动进入/退出看板，不需人工维护列表
- 无自然搜索流量或无订单的 PDP 也保留，标记为"无数据"，便于发现盲点

预计量级：需先拉一次 Shopify 产品列表确认（通常在 200–500 之间，会直接影响前端分页/性能方案）。

---

## 3. 核心指标

按现有分类页看板的三个板块对齐：

### 3.1 SEO 表现（数据源：GSC）

- 点击数、曝光数、CTR、平均排名（周度）
- 命中关键词 Top N（查询词、点击、曝光、排名）
- 按设备、按国家拆分
- 对比：环比上周、环比 Q 开始

### 3.2 流量与行为（数据源：GA4 + Shopify 登陆页报表）

- 页面浏览数、独立访客、会话数
- 平均停留时长、跳出率
- 关键事件：`view_item`、`add_to_cart`、`begin_checkout`
- 流量来源拆分（自然搜索 / 付费 / 直接 / 社交 / 推荐）

### 3.3 转化与收入（数据源：Shopify 订单）

- 订单数、销售额（总额 / 净额）
- 以 PDP 为落地页的转化率
- 产品维度销售（产品实际被下单次数，不一定来自该 PDP 落地）
- 客单价、复购率（如有 customer id）

### 3.4（暂不做）库存与商品属性

本期不纳入。若后续需要，单独补充数据源（Shopify 产品 API）。

---

## 4. 目标对比维度

按用户确认，**PDP 不单独设目标**，对比在聚合层完成：

- **按品牌聚合**：品牌 = 供应商/工厂品牌（Irontech / WM / Piper / SE Doll 等）
  - 需要新增 `config/brand-mapping.csv`，字段：`product_handle, brand, series`
  - 初始版本可由 ETL 根据产品标题前缀或标签做规则匹配，人工修正
- **按 collection 聚合**：一个 PDP 可属于多个 collection，需要多对多映射
  - 来自 Shopify 的产品 ↔ collection 关系表（需导出）
- **按自定义内部分组聚合**（可选）：如"精品系列"、"新品系列"、"促销系列"，同样通过 mapping 文件配置

Q1–Q4 目标只在品牌/collection/内部分组层存在，PDP 自身不承载目标。

---

## 5. 主视图设计

两种视图**并存**，通过 tab 切换：

### 5.1 聚合视图（首屏默认）

- 顶部：品牌维度卡片（每个品牌一张卡，展示总点击 / 总 PV / 总订单 / 总销售 / vs Q1目标完成度）
- 中部：按 collection 的堆叠柱状图或气泡图
- 点击任一品牌/分类 → 下钻到该分组下的 PDP 列表（即排行榜视图的子集）

### 5.2 全量 PDP 排行榜

- 大表格，每行一个 PDP
- 列：产品名、handle、所属品牌、所属 collection（可能多个）、Owner、点击、PV、会话、订单、销售额、转化率、平均排名、周环比
- 支持：按任意列排序、按品牌/collection/Owner 筛选、按产品名搜索
- 支持导出 CSV

### 5.3 单 PDP 详情抽屉（点击任一行打开）

- 该 PDP 的周度趋势（点击、PV、订单 4 条线）
- 该 PDP 当前命中的 Top 关键词
- 该 PDP 的设备/国家拆分
- 该 PDP 近期订单列表

---

## 6. 数据更新节奏

沿用周度：与现有分类页看板保持同一批 CSV 导入窗口，同一个"刷新数据"按钮触发 ETL。

---

## 7. 数据源与 ETL 改造

### 7.1 新增/需补充的数据源

| 数据源 | 现状 | 需补充 |
|---|---|---|
| GSC「网页」维度 | 已有 collection 级 | 需额外导出 PDP 级（`/products/*`）的周度 CSV |
| GSC「查询 × 页面」 | 已有 collection 级 | 需导出每个 PDP 的查询词 |
| GA4 PDP 页面浏览 | 已有全站 `页面浏览数.csv` | 可直接复用，按 URL path 过滤 `/products/` |
| GA4 PDP 事件 | 未导出 | 需新增 `view_item / add_to_cart / begin_checkout` 按 `page_path` 的周度导出 |
| Shopify 登陆页报表 | 已有全站 | 过滤 `/products/` 路径即可 |
| 订单归因 | 有 CSV 但 tag 字段混乱 | 见 7.3 |
| 产品 → collection 映射 | 无 | 需从 Shopify Admin 导出产品列表（含 collections 字段） |
| 产品 → 品牌映射 | 无 | 需人工梳理 `brand-mapping.csv` |

### 7.2 CSV 目录约定（建议）

```
landing-page-data/
  products/                            # 新增，PDP 级数据
    {product-handle}/
      w{NN}_{YYYY-MM-DD}/
        网页.csv
        查询数.csv
        设备.csv
        国家_地区.csv
        事件.csv                      # GA4 事件（view_item/add_to_cart/checkout）
```

考虑到 PDP 数量大（可能 300+），建议 GSC 导出时**不按单 PDP 分目录**，而是一份总表：

```
landing-page-data/
  products-gsc/
    w{NN}_{YYYY-MM-DD}/
      网页.csv        # 一行一个 PDP，含 URL/点击/曝光/CTR/排名
      查询数.csv      # 一行一个 PDP×查询词
```

这样只需每周导出 2 份 CSV，而不是 300 个目录，ETL 侧再拆分到每个 PDP 的数据结构。

### 7.3 订单归因修正

当前 `订单标记` 字段存的是运营促销分类（xcottonsp、加急快递…），无法用来做 PDP 归因。建议：

- **首选**：直接用「产品标题」列匹配 Shopify 产品名，做精确/模糊匹配到 `product_handle`
- **备选**：Shopify 订单导出增加 `Line Item Product Handle` 或 `Product ID` 字段
- PDP 销售 = 该 PDP 的产品出现在订单 line item 中的销售额（不强依赖 landing page 归因）
- PDP 转化率 = (以该 PDP 为 landing page 的订单 / 该 PDP 会话数)

需要同时区分"产品销量"和"PDP 落地转化"两个口径。

### 7.4 新增 aggregate_pdp.py

- 独立于现有 `aggregate_detail.py`，避免耦合
- 输出 `dashboard_pdp.json`
- 结构建议：
  ```json
  {
    "stats": { "totalProducts": N, "totalBrands": N, "weeks": [...] },
    "brands": { "Irontech": { "products": [...], "q1_goals": {...} } },
    "collections": { "full-doll": { "products": [...] } },
    "products": {
      "{handle}": {
        "meta": { "title", "brand", "series", "collections": [...], "url" },
        "weekly": { "w{NN}_{date}": { "gsc": {...}, "ga4": {...}, "orders": {...} } }
      }
    }
  }
  ```

### 7.5 前端

- 沿用 `dashboard.html` 的单文件 SPA 风格，新增 `dashboard_pdp.html`
- 或者：在现有看板增加"详情页"tab，共享 server / Chart.js / 样式

---

## 8. 配置文件新增清单

| 文件 | 目的 | 字段 |
|---|---|---|
| `config/brand-mapping.csv` | PDP → 品牌/系列 映射 | product_handle, product_title, brand, series, internal_group |
| `config/product-collection.csv` | PDP → collection 多对多 | product_handle, collection_slug |
| `config/brand-target-2026.csv` | 品牌级 Q1–Q4 目标 | brand, q1_traffic, q1_revenue, q1_orders, … |

---

## 9. 待用户进一步确认的点

1. **数据导出可行性**：GSC/GA4 能否按 PDP 维度稳定导出？（GSC 的 URL 维度可以，但需确认导出自动化方案）
2. **订单行项数据**：Shopify 订单导出能否改为带 line item 和 product handle 的格式？这是做准 PDP 销售归因的前提。
3. **产品–collection 映射频率**：是否需要每周同步？还是月度即可？
4. **品牌字典规模**：LinkDolls 上总共代理多少个品牌？手工整理可行吗？
5. **PDP 个体目标诉求**：真的完全不设 PDP 级目标吗？还是对 Top 20 主推品可以单独设目标？

---

## 10. 里程碑建议

1. **M1 数据就绪**（1 周）
   - 导出一次 PDP 全量 GSC + GA4 + 产品列表
   - 产出 brand/collection mapping 初稿
2. **M2 ETL v1**（1 周）
   - `aggregate_pdp.py` 跑通，输出 `dashboard_pdp.json`
3. **M3 前端 v1**（1 周）
   - 聚合视图 + 排行榜视图 + 详情抽屉
4. **M4 订单归因修正**（与 M2/M3 并行）
   - 修正订单 line item 归因，替换掉当前按 order tag 的方案
