#!/usr/bin/env python3
"""
将 dashboard_detail.json 内嵌到 dashboard_collection.html
运行前提: aggregate_detail.py 已生成最新的 dashboard_detail.json
"""
import os, re

BASE = os.path.dirname(os.path.abspath(__file__))

# 读取原始模板（从 git 恢复的 1354 行版本）
# 首次运行后会覆盖，所以用标记判断是否已内嵌
html_path = os.path.join(BASE, 'dashboard_collection.html')
json_path = os.path.join(BASE, 'dashboard_detail.json')

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

with open(json_path, 'r', encoding='utf-8') as f:
    json_data = f.read().strip()

# 如果已经内嵌过，替换旧数据
if 'window.__COLLECTION_DATA__' in html:
    html = re.sub(
        r'window\.__COLLECTION_DATA__\s*=\s*\{.*?\};',
        f'window.__COLLECTION_DATA__ = {json_data};',
        html, count=1, flags=re.DOTALL
    )
else:
    # 首次内嵌：替换 fetch 逻辑，注入数据
    html = html.replace(
        "const r = await fetch('dashboard_detail.json');",
        "// data loaded from embedded script below"
    ).replace(
        "if (!r.ok) throw new Error('HTTP ' + r.status + ': 无法加载 dashboard_detail.json');",
        ""
    ).replace(
        "RAW = await r.json();",
        "RAW = window.__COLLECTION_DATA__;"
    ).replace(
        "const response = await fetch('/api/refresh');",
        "// refresh disabled on static hosting"
    )
    script_idx = html.index('<script>')
    inject = f'<script>window.__COLLECTION_DATA__ = {json_data};</script>\n'
    html = html[:script_idx] + inject + html[script_idx:]

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✓ dashboard_collection.html 已更新 ({len(html):,} bytes)")
