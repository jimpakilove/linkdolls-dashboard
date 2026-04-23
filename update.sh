#!/bin/bash
# LinkDolls 看板一键更新脚本
# 用法: 终端执行 bash "/Users/apple/Desktop/linkdolls dashboard/update.sh"

cd "/Users/apple/Desktop/linkdolls dashboard"

echo "============================================================"
echo "LinkDolls 看板一键更新"
echo "============================================================"

# 1. 更新分类页看板（生成 dashboard_detail.json）
echo ""
echo "📊 更新分类页看板..."
python3 landing-page-data/aggregate_detail.py
if [ $? -ne 0 ]; then
    echo "❌ 分类页看板更新失败"
    read -p "按回车退出..."
    exit 1
fi

# 2. 更新详情页看板（生成 dashboard.html）
echo ""
echo "📦 更新详情页看板..."
python3 landing-page-data/update_pdp.py
if [ $? -ne 0 ]; then
    echo "❌ 详情页看板更新失败"
    read -p "按回车退出..."
    exit 1
fi

# 3. 推送到 GitHub
echo ""
echo "🚀 推送到 GitHub..."
git add -f landing-page-data/dashboard.html \
          landing-page-data/dashboard_collection.html \
          landing-page-data/dashboard_detail.json
git commit -m "update $(date +%Y-%m-%d)"
git push

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "✅ 全部完成！数据已推送到 GitHub"
    echo "============================================================"
else
    echo ""
    echo "❌ Git 推送失败，请检查网络"
fi

read -p "按回车退出..."
