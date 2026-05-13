#!/bin/bash
# 每周数据更新 & 推送脚本
# 用法：bash update_and_push.sh
# 或双击运行（需先授权：chmod +x update_and_push.sh）

set -e  # 任何步骤失败立即停止

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/landing-page-data"

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

# ── 步骤 3：推送到 GitHub ──────────────────────────────────────
echo ""
echo "🚀 步骤 3/3  推送到 GitHub..."
cd "$SCRIPT_DIR"

# 取本周周次作为 commit 信息（ISO week number）
WEEK_NUM=$(python3 -c "from datetime import date; print(f'W{date.today().isocalendar()[1]}')")
COMMIT_MSG="data: 更新 ${WEEK_NUM} 周数据 $(date '+%Y-%m-%d')"

git add landing-page-data/dashboard.html \
        landing-page-data/dashboard_detail.json \
        landing-page-data/top50_data.json \
        landing-page-data/category_data.json \
        landing-page-data/dashboard_top50.html

git diff --cached --quiet && echo "⚠ 没有变更，跳过 commit" || \
    git commit -m "$COMMIT_MSG"

git push origin main

echo ""
echo "============================================================"
echo "  ✅ 全部完成！"
echo "============================================================"
