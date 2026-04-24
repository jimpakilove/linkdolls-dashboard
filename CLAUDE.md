# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An internal SEO/analytics dashboard for the LinkDolls Shopify store. It tracks weekly GSC (Google Search Console) and GA4 data across 38 product collection landing pages, visualizing traffic, rankings, conversions, and revenue against Q1 2026 goals.

## Running the Project

All scripts live inside `landing-page-data/`. Run from that directory:

```bash
# Start the local HTTP server (port 8765)
python3 server.py

# Regenerate dashboard_detail.json from all CSVs
python3 aggregate_detail.py

# Then open in browser:
# http://localhost:8765/dashboard.html
```

The dashboard's "刷新数据" (Refresh Data) button calls `GET /api/refresh`, which triggers `aggregate_detail.py` via subprocess and reloads the page.

There are no tests, no linting tools, and no build step.

## Architecture

### Data Flow

```
CSV files (weekly imports) + config/target-2026.csv + orders CSV
        ↓
aggregate_detail.py  (ETL pipeline, pure Python stdlib)
        ↓
landing-page-data/dashboard_detail.json  (~4 MB)
        ↓
server.py  (http.server on port 8765)
        ↓
dashboard.html  (single-file SPA, loads JSON via fetch, renders with Chart.js)
```

### Input Data Structure

Weekly CSVs are organized as `landing-page-data/{category-slug}/w{NN}_{YYYY-MM-DD}/`:
- `网页.csv` — GSC: top page clicks/impressions/rank
- `查询数.csv` — GSC: keyword queries, rank, CTR
- `设备.csv` — GSC: by device
- `国家_地区.csv` — GSC: by country
- `购买历程_设备类别.csv` — GA4: purchase funnel by device
- `页面点击数.csv` — GA4: page element clicks
- `电子商务购买_商品名称*.csv` — GA4: add-to-cart product list

Global pageview files live in `landing-page-data/pageviews/`:
- `页面浏览数{date}.csv` — GA4 pageviews by URL path
- `按登陆页面划分的访问量*.csv` — Shopify sessions/visitors by landing page

### Key Files

| File | Role |
|---|---|
| `config/target-2026.csv` | Master config: maps each `/collections/{slug}` to owner (`负责人`) and Q1–Q4 traffic/revenue targets |
| `orders/orders_detail_2026_Q1_with_tags.csv` | Shopify order export; orders are tagged with their landing page URL for revenue attribution |
| `landing-page-data/aggregate_detail.py` | Primary ETL — reads all CSVs, writes `dashboard_detail.json` |
| `landing-page-data/aggregate_data.py` | Legacy ETL (simpler format) — produces `dashboard_data.json`; not actively used |
| `landing-page-data/server.py` | Local static file server + `/api/refresh` endpoint |
| `landing-page-data/dashboard.html` | ~1,300-line single-file SPA: all CSS, HTML, and JS in one file |
| `landing-page-data/dashboard_detail.json` | Generated output consumed by the dashboard |

### dashboard_detail.json Schema

```json
{
  "stats": { "categories": [], "weeks": [], "totalCategories": N, "totalWeeks": N },
  "config": { "<category>": { "owner": "...", "q1_traffic_goal": N, "q1_revenue_goal": N } },
  "data": {
    "<category>": {
      "<weekFolder>": {
        "gsc": { "clicks": N, "impressions": N, "ctr": N, "position": N },
        "ga4": { "pageviews": N },
        "landingPage": { "sessions": N, "visitors": N },
        "queries": [...],
        "devices": [...],
        "countries": [...],
        "clicks": [...],
        "conversion": { "mobile": {...}, "desktop": {...} },
        "revenue": { "total": N, "orders": N },
        "cartAdds": [...],
        "config": { "owner": "...", "q1_traffic_goal": N },
        "hasData": true
      }
    }
  }
}
```

### Revenue Attribution

Orders in `orders_detail_2026_Q1_with_tags.csv` are attributed to a category using exact string matching on the `Order tag` column against `/collections/{slug}`.

### Week Visibility Control

`dashboard.html` has a hardcoded `currentWeek = 14` constant (around line 678) that controls which weeks are visible in the UI. Update this number when advancing to new weeks.

## Important Caveats

**Hardcoded absolute paths**: `aggregate_detail.py` contains Mac-specific absolute paths (e.g. `/Users/apple/Desktop/linkdolls dashboard/...`). If running on a different machine, update the path constants at the top of that file.

**Chinese-language data**: All CSV column headers, file names, and UI labels are in Simplified Chinese. Column name strings in the Python ETL code must exactly match the CSV headers.
