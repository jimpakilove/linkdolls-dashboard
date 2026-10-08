#!/bin/bash
# 每周数据更新 & 推送脚本
# 用法：bash update_and_push.sh
# 或双击运行（需先授权：chmod +x update_and_push.sh）

set -euo pipefail  # 任何步骤失败立即停止

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/landing-page-data"

# 不把其他工作已暂存的文件混入本次发布。
cd "$SCRIPT_DIR"
if ! git diff --cached --quiet; then
    echo "❌ 暂存区有其他改动，请先处理后再运行，避免误提交。"
    exit 1
fi
if [ "$(git branch --show-current)" != "main" ]; then
    echo "❌ 请在 main 分支运行，避免推送的不是刚生成的数据。"
    exit 1
fi

echo "============================================================"
echo "  LinkDolls 数据看板 — 每周更新"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"

# ── 步骤 1：PDP 看板（Top300 + 类别对比）──────────────────────
echo ""
echo "📦 步骤 1/3  更新 PDP 看板数据..."
cd "$DATA_DIR"
python3 update_pdp.py

# ── 步骤 2：分类页看板 ─────────────────────────────────────────
echo ""
echo "📊 步骤 2/3  更新分类页看板数据..."
python3 aggregate_detail.py
python3 -B -m unittest test_traffic_data.py
python3 -B test_category_revenue.py
python3 -B test_revenue_aggregation.py
if command -v node >/dev/null 2>&1; then
    node test_traffic_render.cjs
fi

# ── 步骤 3：推送到 GitHub ──────────────────────────────────────
echo ""
echo "🚀 步骤 3/3  推送到 GitHub..."
cd "$SCRIPT_DIR"

# 使用数据中的最新周期，不把运行日期所在周误当作数据周。
WEEK_NUM=$(python3 -c "import json; d=json.load(open('landing-page-data/dashboard_detail.json')); w=max(d['stats']['weeks'], key=lambda w:w.split('_',1)[1]); print(w.split('_')[0].upper())")
COMMIT_MSG="data: 更新 ${WEEK_NUM} 周数据 $(date '+%Y-%m-%d')"

git add landing-page-data/dashboard.html \
        landing-page-data/dashboard_detail.json \
        landing-page-data/top50_data.json \
        landing-page-data/category_data.json \
        landing-page-data/category_revenue.json \
        landing-page-data/dashboard_top50.html \
        landing-page-data/dashboard_collection.html \
        landing-page-data/dashboard_click_rate.html \
        landing-page-data/aggregate_detail.py \
        landing-page-data/update_pdp.py \
        landing-page-data/test_traffic_data.py \
        landing-page-data/test_traffic_render.cjs \
        landing-page-data/test_category_revenue.py \
        landing-page-data/test_revenue_aggregation.py \
        update_and_push.sh

git diff --cached --quiet && echo "⚠ 没有变更，跳过 commit" || \
    git commit -m "$COMMIT_MSG"

git push origin main

echo ""
echo "============================================================"
echo "  ✅ 全部完成！"
echo "============================================================"
