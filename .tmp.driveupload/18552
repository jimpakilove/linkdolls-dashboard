# LinkDolls 数据看板

> LinkDolls Shopify 店铺内部 SEO/分析看板系统，追踪 38 个产品分类落地页的流量、排名、转化与收入表现。

---

## 📊 项目简介

本项目是一个内部数据分析看板，整合 **Google Search Console (GSC)**、**Google Analytics 4 (GA4)** 和 **Shopify 订单数据**，为 LinkDolls 运营团队提供：

- **分类页表现总览**：38 个产品 collection 的周度流量、收入、排名趋势
- **PDP 详情页分析**：Top 300 产品页面的搜索表现与转化数据
- **目标达成追踪**：对照 2026 年 Q1–Q4 的流量与收入目标
- **关键词洞察**：各分类的搜索查询、设备分布、地域分布

---

## 🚀 快速启动

### 1. 启动本地服务器

```bash
cd landing-page-data
python3 server.py
```

服务器运行在 `http://localhost:8765`

### 2. 刷新数据（生成最新看板）

```bash
# 分类页看板
python3 landing-page-data/aggregate_detail.py

# PDP 看板
python3 landing-page-data/update_pdp.py
```

### 3. 一键更新 & 推送（推荐）

```bash
bash update_and_push.sh
```

或双击 `update.sh`（macOS）运行。

---

## 📁 目录结构

```
linkdolls-dashboard/
├── config/
│   └── target-2026.csv          # 38 个分类的负责人与季度目标
├── landing-page-data/
│   ├── aggregate_detail.py      # 分类页 ETL（主数据管道）
│   ├── update_pdp.py            # PDP 看板生成器
│   ├── server.py                # 本地 HTTP 服务器 + /api/refresh
│   ├── dashboard.html           # PDP 看板（单文件 SPA）
│   ├── dashboard_detail.json    # 分类页看板数据源（~20MB）
│   ├── {category-slug}/         # 38 个分类的原始 CSV 数据
│   │   └── w{NN}_{YYYY-MM-DD}/  # 每周 GSC + GA4 导出
│   │       ├── 网页.csv
│   │       ├── 查询数.csv
│   │       ├── 设备.csv
│   │       ├── 国家_地区.csv
│   │       ├── 购买历程_设备类别.csv
│   │       ├── 页面点击数.csv
│   │       └── 电子商务购买_商品名称*.csv
│   └── pageviews/               # 全局页面浏览数据
├── keywords/                    # 关键词数据（xlsx）
├── orders/
│   └── 订单明细表导出*.csv       # Shopify 订单，带 landing page tag
├── CLAUDE.md                    # 技术细节（供 AI 助手参考）
├── update.sh                    # 一键更新脚本（macOS 双击）
└── update_and_push.sh           # 每周更新 + GitHub 推送脚本
```

---

## 🔄 数据流程

```
每周 CSV 导入（GSC + GA4 + Shopify 订单）
        ↓
config/target-2026.csv（目标配置）
        ↓
aggregate_detail.py（纯 Python 标准库 ETL）
        ↓
dashboard_detail.json（~20MB 聚合数据）
        ↓
server.py（http.server :8765）
        ↓
dashboard.html（Chart.js 单页应用，浏览器渲染）
```

---

## 📈 看板功能

### 分类页看板 (`dashboard.html`)

| 功能 | 说明 |
|---|---|
| 总览表格 | 38 个分类的点击量、曝光、排名、收入、目标达成率 |
| 趋势图 | 各分类的周度流量/收入趋势折线图 |
| 设备分布 | 移动端 vs 桌面端转化漏斗对比 |
| 关键词排名 | 各分类 Top 搜索查询及排名变化 |
| 时间粒度 | 支持单周视图与 4 周周期汇总切换 |
| 目标追踪 | 对比 Q1–Q4 流量与收入目标，显示达成进度条 |

### PDP 看板 (`dashboard.html`)

| 功能 | 说明 |
|---|---|
| Top 300 产品 | 按点击量排序的产品页面表现 |
| 收入归因 | 产品级收入与订单数统计 |
| 类别对比 | 不同产品类型的横向表现对比 |
| 4 周粒度 | 支持切换单周 / 4 周周期趋势 |

---

## ⚙️ 配置说明

### 修改季度目标

编辑 `config/target-2026.csv`：

```csv
slug,owner,q1_traffic_goal,q1_revenue_goal,...
life-like-sex-doll,张三,50000,15000,...
```

### 调整可见周数

编辑 `landing-page-data/dashboard.html` 第 ~678 行：

```javascript
const currentWeek = 14;  // 修改为你需要的最新周次
```

### 收入归因规则

订单通过 `Order tag` 列中的 `/collections/{slug}` 字符串匹配，归属到对应分类。

---

## 📝 每周数据更新流程

1. **导出数据**
   - GSC：按分类导出「网页」「查询数」「设备」「国家/地区」
   - GA4：导出「购买历程」「页面点击数」「电子商务购买」
   - Shopify：导出订单明细（确保包含 Order tags）

2. **放入目录**
   - 将 CSV 文件放入对应分类的 `w{周次}_{日期}/` 文件夹
   - 将订单 CSV 放入 `orders/` 目录

3. **运行更新**
   ```bash
   bash update_and_push.sh
   ```

4. **查看看板**
   - 本地：`http://localhost:8765/dashboard.html`
   - GitHub Pages：推送后自动部署

---

## 🛠️ 技术栈

- **后端**：Python 3（纯标准库，无依赖）
- **前端**：原生 HTML/CSS/JS + Chart.js
- **服务器**：Python `http.server`
- **部署**：GitHub Pages（静态文件托管）

---

## ⚠️ 已知限制

1. **硬编码路径**：`aggregate_detail.py` 顶部包含 macOS 绝对路径（`/Users/apple/Desktop/...`），在其他机器运行前需修改
2. **中文 CSV 表头**：Python 脚本中的列名字符串必须与 CSV 完全一致
3. **无测试/构建**：项目无单元测试、lint 或构建步骤，纯脚本驱动
4. **单用户**：本地服务器仅支持本机访问，无多用户或权限控制

---

## 📜 更新日志

| 日期 | 更新内容 |
|---|---|
| 2026-05-18 | 产品代码聚合（a512/a599 等变体合并） |
| 2026-05-13 | Top300 支持 4 周周期粒度切换 |
| 2026-05-10 | 兼容英文表头 CSV + BOM 编码修复 |
| 2026-04-28 | 分类页看板增加 4 周周期时间颗粒度 |
| 2026-04-15 | 订单去重逻辑修复，分类收入归因优化 |

---

## 🤝 维护

- **数据负责人**：运营团队
- **技术维护**：开发团队
- **问题反馈**：通过内部渠道或提交 Issue

---

*最后更新：2026-05-19*
