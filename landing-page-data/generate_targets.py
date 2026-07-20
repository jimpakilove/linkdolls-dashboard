#!/usr/bin/env python3
"""
季度目标追踪报表 ETL
- 读取 config/target-2026.csv 获取季度目标
- 读取 dashboard_detail.json 获取实际流量和收入
- 按季度聚合，输出 targets_data.json
"""
import os, json, csv, re
from datetime import datetime
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.resolve()
CONFIG_PATH = Path('/Users/apple/Desktop/linkdolls dashboard/config/target-2026.csv')
DETAIL_PATH = BASE / 'dashboard_detail.json'
OUTPUT_PATH = BASE / 'targets_data.json'

def parse_num(val):
    if not val:
        return 0
    s = str(val).strip().replace('$', '').replace(',', '').replace(' ', '').replace('%', '')
    try:
        return float(s)
    except:
        return 0

def load_targets():
    targets = []
    seen = set()
    with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('着陆页', '').strip()
            if not url:
                continue
            if url.startswith('/collections/'):
                slug = url.replace('/collections/', '')
            elif url == '/linkdolls.com':
                slug = 'linkdolls.com'
            elif url.startswith('/pages/'):
                slug = url.replace('/pages/', '')
            else:
                slug = url.strip('/')
            if slug in seen:
                continue
            seen.add(slug)
            targets.append({
                'slug': slug, 'url': url,
                'owner': row.get('负责人', '-').strip(),
                'lastYearTraffic': int(parse_num(row.get('2025有效流量（排除印度）', 0))),
                'lastYearRevenue': parse_num(row.get('25年销售额', 0)),
                'lastYearOrders': int(parse_num(row.get('25年订单数', 0))),
                'lastYearCVR': parse_num(row.get('25年转化率', 0)),
                'yearTrafficGoal': int(parse_num(row.get('全年流量目标', 0))),
                'yearRevenueGoal': parse_num(row.get('全年销售金额', 0)),
                'yearCVRGoal': parse_num(row.get('全年转化率（参考）', 0)),
                'yearOrderGoal': int(parse_num(row.get('全年订单数（参考）', 0))),
                'quarters': {
                    q: {
                        'trafficGoal': int(parse_num(row.get(f'{q.lower()}流量目标', 0))),
                        'cvrGoal': parse_num(row.get(f'{q.lower()}转化率', 0)),
                        'orderGoal': int(parse_num(row.get(f'{q.lower()}订单数', 0))),
                        'revenueGoal': parse_num(row.get(f'{q.lower()}销售金额', 0)),
                    } for q in ['Q1','Q2','Q3','Q4']
                }
            })
    print(f"加载目标: {len(targets)} 个页面")
    return targets

def week_to_quarter(week_start_str):
    if not week_start_str:
        return None
    try:
        dt = datetime.strptime(week_start_str, '%Y-%m-%d')
        m = dt.month
        return 'Q1' if m <= 3 else 'Q2' if m <= 6 else 'Q3' if m <= 9 else 'Q4'
    except:
        return None

def load_actuals(targets):
    with open(DETAIL_PATH, 'r', encoding='utf-8') as f:
        detail = json.load(f)
    data = detail.get('data', {})
    week_folders = detail.get('stats', {}).get('weeks', [])
    week_quarter_map = {}
    for wf in week_folders:
        m = re.match(r'w(\d+)_(\d{4}-\d{2}-\d{2})', wf)
        if m:
            q = week_to_quarter(m.group(2))
            if q:
                week_quarter_map[wf] = q

    results = []
    for t in targets:
        slug = t['slug']
        cat_data = data.get(slug, {})
        actuals = {q: {'traffic': 0, 'revenue': 0.0, 'orders': 0} for q in ['Q1','Q2','Q3','Q4']}

        for week_folder, week_data in cat_data.items():
            q = week_quarter_map.get(week_folder)
            if not q:
                continue
            clicks = week_data.get('gsc', {}).get('clicks', 0)
            actuals[q]['traffic'] += clicks

        # Revenue/orders are stored per-quarter in every week's data; take first week
        for week_folder, week_data in cat_data.items():
            rev = week_data.get('revenue', {})
            for q in ['Q1','Q2','Q3','Q4']:
                q_rev = rev.get(q, {})
                actuals[q]['revenue'] = q_rev.get('totalSales', 0)
                actuals[q]['orders'] = q_rev.get('orders', 0)
            break

        for q in ['Q1','Q2','Q3','Q4']:
            a = actuals[q]
            a['cvr'] = round(a['orders'] / a['traffic'] * 100, 2) if a['traffic'] > 0 else 0
            goals = t['quarters'][q]
            a['trafficRate'] = round(a['traffic'] / goals['trafficGoal'] * 100, 1) if goals['trafficGoal'] > 0 else 0
            a['revenueRate'] = round(a['revenue'] / goals['revenueGoal'] * 100, 1) if goals['revenueGoal'] > 0 else 0
            a['orderRate'] = round(a['orders'] / goals['orderGoal'] * 100, 1) if goals['orderGoal'] > 0 else 0

        year_actual = {
            'traffic': sum(actuals[q]['traffic'] for q in ['Q1','Q2','Q3','Q4']),
            'revenue': round(sum(actuals[q]['revenue'] for q in ['Q1','Q2','Q3','Q4']), 2),
            'orders': sum(actuals[q]['orders'] for q in ['Q1','Q2','Q3','Q4']),
        }
        year_actual['cvr'] = round(year_actual['orders'] / year_actual['traffic'] * 100, 2) if year_actual['traffic'] > 0 else 0

        entry = {
            'slug': slug, 'url': t['url'], 'owner': t['owner'],
            'lastYearTraffic': t['lastYearTraffic'],
            'lastYearRevenue': t['lastYearRevenue'],
            'lastYearOrders': t['lastYearOrders'],
            'lastYearCVR': t['lastYearCVR'],
            'yearTrafficGoal': t['yearTrafficGoal'],
            'yearRevenueGoal': t['yearRevenueGoal'],
            'yearCVRGoal': t['yearCVRGoal'],
            'yearOrderGoal': t['yearOrderGoal'],
            'yearActual': year_actual,
            'quarters': {}
        }
        for q in ['Q1','Q2','Q3','Q4']:
            entry['quarters'][q] = {
                'trafficGoal': t['quarters'][q]['trafficGoal'],
                'cvrGoal': t['quarters'][q]['cvrGoal'],
                'orderGoal': t['quarters'][q]['orderGoal'],
                'revenueGoal': t['quarters'][q]['revenueGoal'],
                'actualTraffic': actuals[q]['traffic'],
                'actualRevenue': round(actuals[q]['revenue'], 2),
                'actualOrders': actuals[q]['orders'],
                'actualCVR': actuals[q]['cvr'],
                'trafficRate': actuals[q]['trafficRate'],
                'revenueRate': actuals[q]['revenueRate'],
                'orderRate': actuals[q]['orderRate'],
            }
        results.append(entry)
    return results

def main():
    print("开始生成季度目标追踪数据...")
    targets = load_targets()
    results = load_actuals(targets)
    output = {
        'pages': results,
        'generatedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(OUTPUT_PATH)
    print(f"输出: {OUTPUT_PATH.name} ({size:,} bytes), {len(results)} 页面")
    for q in ['Q1','Q2','Q3','Q4']:
        tt = sum(r['quarters'][q]['actualTraffic'] for r in results)
        tr = sum(r['quarters'][q]['actualRevenue'] for r in results)
        to = sum(r['quarters'][q]['actualOrders'] for r in results)
        gt = sum(r['quarters'][q]['trafficGoal'] for r in results)
        gr = sum(r['quarters'][q]['revenueGoal'] for r in results)
        go = sum(r['quarters'][q]['orderGoal'] for r in results)
        print(f"  {q}: 流量 {tt}/{gt} ({round(tt/gt*100,1) if gt else 0}%) | 收入 ${tr:,.0f}/${gr:,.0f} | 订单 {to}/{go}")

if __name__ == '__main__':
    main()
