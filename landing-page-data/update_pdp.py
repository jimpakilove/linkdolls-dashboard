#!/usr/bin/env python3
"""
PDP 看板数据更新脚本
用法: python3 update_pdp.py

自动完成:
1. 从 pageviews/电子商务购买_商品名称*.csv 读取产品浏览/加购/结账数据
2. 从 orders/ 目录下最新订单表匹配收入数据（W10-W16 范围）
3. 生成 top50_data.json + category_data.json
4. 重建 dashboard.html（合并详情页看板 + 类别对比 + 分类页看板）
"""

import csv, json, re, glob, os, sys
from collections import defaultdict
from difflib import SequenceMatcher

# ── 配置 ──
BASE = os.path.dirname(os.path.abspath(__file__))
PAGEVIEWS_DIR = os.path.join(BASE, 'pageviews')
ORDERS_DIR = os.path.join(BASE, '..', 'orders')

# 周定义 - 自动从 CSV 文件检测
def detect_weeks():
    """扫描 pageviews/电子商务购买_商品名称*.csv 自动检测可用周"""
    from datetime import datetime, timedelta
    files = glob.glob(os.path.join(PAGEVIEWS_DIR, '电子商务购买_商品名称*.csv'))
    weeks = []
    for f in files:
        # 提取文件名中的日期后缀，如 0302、0413
        m = re.search(r'商品名称(\d{4})\.csv$', f)
        if not m:
            continue
        suffix = m.group(1)  # e.g. "0302"
        month = int(suffix[:2])
        day = int(suffix[2:])
        # 推算完整日期（假设是 2026 年）
        date_str = f'2026-{month:02d}-{day:02d}'
        weeks.append((suffix, date_str))

    weeks.sort(key=lambda x: x[1])  # 按日期排序

    # 计算周编号：第一个 CSV 的日期对应的 ISO 周号
    result = []
    for suffix, date_str in weeks:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        week_num = dt.isocalendar()[1]
        week_name = f'W{week_num}'
        result.append((week_name, suffix, date_str))

    # 最后一周的结束日期 = 最后一周起始 + 7 天
    if result:
        last_dt = datetime.strptime(result[-1][2], '%Y-%m-%d')
        week_end = (last_dt + timedelta(days=7)).strftime('%Y-%m-%d')
    else:
        week_end = '2099-12-31'

    return result, week_end

WEEKS, WEEK_END = detect_weeks()
WEEK_NAMES = [w[0] for w in WEEKS]
WEEK_SUFFIXES = [w[1] for w in WEEKS]
WEEK_STARTS = [w[2] for w in WEEKS]

CAT_NAMES = {
    'f': 'Full Doll 完整娃', 'a': 'Ass 臀部', 't': 'Torso 躯干', 'h': 'Head 头部',
    'p': 'Pussy 内部', 'v': 'Vajankle 足踝', 'l': 'Legs 腿部', 'b': 'Boob 胸部',
    'm': 'Male 男性', 'd': 'Dildo 假阳具', 'other': 'Other 其他'
}

SKIP_ORDER_KW = ['shipping protection', 'route', 'extended warranty', 'custom']


def find_orders_file():
    """找到 orders/ 目录下最新的订单表"""
    candidates = glob.glob(os.path.join(ORDERS_DIR, '订单明细表*.csv'))
    if not candidates:
        print("⚠ 未找到订单文件，收入数据将为空")
        return None
    return max(candidates, key=os.path.getmtime)


def read_ecom_csv(path):
    """读取电子商务购买 CSV（跳过注释头）"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
    header_idx = next((i for i, l in enumerate(lines) if l.startswith('商品名称,')), None)
    if header_idx is None:
        return []
    return list(csv.DictReader(lines[header_idx:]))


def date_to_week(d):
    """日期字符串 -> 周索引，不在范围内返回 -1"""
    if d < WEEK_STARTS[0] or d >= WEEK_END:
        return -1
    for i in range(len(WEEK_STARTS) - 1, -1, -1):
        if d >= WEEK_STARTS[i]:
            return i
    return -1


def get_code_and_cat(name):
    """从产品名称提取代码和类别"""
    m = re.match(r'^([A-Za-z])(\d+)', name.strip())
    if m:
        letter = m.group(1).lower()
        code = letter + m.group(2)
        cat = letter if letter in CAT_NAMES else 'other'
        return code, cat, letter
    return None, 'other', name[0].lower() if name else '?'


def calc_trend(wv):
    """计算趋势"""
    active = [(i, v) for i, v in enumerate(wv) if v > 0]
    if len(active) < 2:
        return 'stable'
    mid = len(active) // 2
    fh = sum(v for _, v in active[:mid]) / max(mid, 1)
    sh = sum(v for _, v in active[mid:]) / max(len(active) - mid, 1)
    if fh == 0 and sh == 0:
        return 'stable'
    ch = (sh - fh) / max(fh, 1)
    if ch > 0.25: return 'accelerating'
    if ch > 0.05: return 'growing'
    if ch > -0.05: return 'stable'
    if ch > -0.25: return 'slowing'
    return 'declining'


def step1_read_ecommerce():
    """步骤1: 读取电子商务购买数据"""
    print("📦 读取电子商务购买数据...")
    n_weeks = len(WEEKS)
    products = {}

    for wi, (wname, suffix, _) in enumerate(WEEKS):
        fname = os.path.join(PAGEVIEWS_DIR, f'电子商务购买_商品名称{suffix}.csv')
        if not os.path.exists(fname):
            print(f"  ⚠ 缺少 {wname} 数据: {fname}")
            continue
        rows = read_ecom_csv(fname)
        count = 0
        for row in rows:
            name = row.get('商品名称', '').strip()
            if not name:
                continue
            if name not in products:
                products[name] = {
                    'name': name,
                    'weeklyViews': [0] * n_weeks, 'weeklyUsers': [0] * n_weeks,
                    'weeklyCarts': [0] * n_weeks, 'weeklyPurchased': [0] * n_weeks,
                    'weeklyRevenue': [0.0] * n_weeks, 'weeklyBounce': [0.0] * n_weeks,
                    'weeklyCheckouts': [0] * n_weeks,
                }
            p = products[name]
            p['weeklyViews'][wi] = int(row.get('查看过的商品数', 0))
            p['weeklyUsers'][wi] = int(row.get('活跃用户', 0))
            p['weeklyCarts'][wi] = int(row.get('加入购物车的商品数', 0))
            p['weeklyPurchased'][wi] = int(row.get('已购买的商品数', 0))
            p['weeklyRevenue'][wi] = float(row.get('商品收入', 0))
            p['weeklyBounce'][wi] = round(float(row.get('跳出率', 0)) * 100, 1)
            p['weeklyCheckouts'][wi] = int(row.get('结账的商品数', 0))
            count += 1
        print(f"  ✓ {wname}: {count} 产品")

    print(f"  合计: {len(products)} 个唯一产品")
    return products


def step2_classify_and_rank(products):
    """步骤2: 分类、计算聚合指标、排名"""
    print("📊 计算排名和趋势...")
    n_weeks = len(WEEKS)

    for name, p in products.items():
        code, cat, first = get_code_and_cat(name)
        p['code'] = code
        p['category'] = cat
        p['firstChar'] = first
        p['totalViews'] = sum(p['weeklyViews'])
        p['totalUsers'] = sum(p['weeklyUsers'])
        p['totalCarts'] = sum(p['weeklyCarts'])
        p['totalCheckouts'] = sum(p['weeklyCheckouts'])
        p['totalPurchased'] = sum(p['weeklyPurchased'])
        p['totalRevenue'] = round(sum(p['weeklyRevenue']), 2)
        p['weeklyRevenue'] = [round(x, 2) for x in p['weeklyRevenue']]
        tv = p['totalViews']
        p['bounceRate'] = round(sum(p['weeklyBounce'][i] * p['weeklyViews'][i] for i in range(n_weeks)) / tv, 1) if tv > 0 else 0

    all_sorted = sorted(products.values(), key=lambda x: -x['totalViews'])
    cat_products = defaultdict(list)
    for p in all_sorted:
        cat_products[p['category']].append(p)

    # Overall ranks
    for rank, p in enumerate(all_sorted, 1):
        p['rank'] = rank
    for cat, prods in cat_products.items():
        for rank, p in enumerate(prods, 1):
            p['catRank'] = rank

    # Weekly ranks
    for wi in range(n_weeks):
        ws = sorted(all_sorted, key=lambda x: -x['weeklyViews'][wi])
        for rank, p in enumerate(ws, 1):
            if 'ranks' not in p: p['ranks'] = [None] * n_weeks
            p['ranks'][wi] = rank if p['weeklyViews'][wi] > 0 else None

    for cat, prods in cat_products.items():
        for wi in range(n_weeks):
            ws = sorted(prods, key=lambda x: -x['weeklyViews'][wi])
            for rank, p in enumerate(ws, 1):
                if 'catRanks' not in p: p['catRanks'] = [None] * n_weeks
                p['catRanks'][wi] = rank if p['weeklyViews'][wi] > 0 else None

    # Trends, WoW, streak, tags
    last = n_weeks - 1
    prev = last - 1
    for p in all_sorted:
        wv = p['weeklyViews']
        p['trend'] = calc_trend(wv)
        p['wow'] = round((wv[last] - wv[prev]) / wv[prev] * 100, 1) if wv[prev] > 0 else 0
        r = p['ranks']
        p['rankDelta'] = (r[prev] - r[last]) if (r[last] and r[prev]) else 0
        streak = 0
        for i in range(last, 0, -1):
            if r[i] and r[i - 1] and r[i] < r[i - 1]:
                streak += 1
            else:
                break
        p['streak'] = streak
        p['bestRank'] = min((x for x in r if x), default=999)
        tags = []
        if wv[last] > 0 and all(v == 0 for v in wv[:last]): tags.append('新进榜')
        if p['wow'] > 50: tags.append('爆发')
        if streak >= 2: tags.append('连升')
        tv = p['totalViews']
        if tv > 0 and p['totalCarts'] / tv * 100 > 5: tags.append('转化待优化')
        p['tags'] = tags

    # Prefix benchmarks
    prefix_groups = defaultdict(list)
    for p in all_sorted:
        prefix_groups[p['category']].append(p['totalViews'])
    prefixBench = {cat: round(sum(vl) / len(vl), 1) for cat, vl in prefix_groups.items()}
    for p in all_sorted:
        p['prefixBench'] = prefixBench.get(p['category'], 0)
        p['prefixTotal'] = len(prefix_groups.get(p['category'], []))

    # Select needed products (overall top50 + per-category top50)
    needed = set(p['name'] for p in all_sorted[:50])
    active_categories = []
    for cat, prods in cat_products.items():
        if len(prods) >= 3:
            active_categories.append(cat)
            for p in prods[:50]:
                needed.add(p['name'])

    print(f"  ✓ 总榜 Top50 + {len(active_categories)} 个类别 = {len(needed)} 个产品")
    return all_sorted, cat_products, needed, active_categories, prefixBench


def step3_match_orders(products, needed):
    """步骤3: 匹配订单收入"""
    orders_file = find_orders_file()
    if not orders_file:
        return

    print(f"💰 匹配订单收入: {os.path.basename(orders_file)}")
    n_weeks = len(WEEKS)

    code_to_names = defaultdict(list)
    for n in needed:
        p = products[n]
        if p.get('code'):
            code_to_names[p['code']].append(n)

    def extract_code(title):
        m = re.match(r'^([A-Za-z]\d+)', title.strip())
        return m.group(1).lower() if m else None

    def match_name(order_title):
        code = extract_code(order_title)
        if not code: return None
        cands = code_to_names.get(code, [])
        if len(cands) == 1: return cands[0]
        if len(cands) > 1:
            ot = order_title.lower().strip()[:80]
            best, best_r = None, 0
            for c in cands:
                r = SequenceMatcher(None, ot, c.lower()[:80]).ratio()
                if r > best_r: best, best_r = c, r
            return best
        return None

    with open(orders_file, 'r', encoding='utf-8-sig') as f:
        raw_rows = list(csv.DictReader(f))

    seen = set()
    name_weekly_rev = defaultdict(lambda: [0.0] * n_weeks)
    name_week_orders = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    for r in raw_rows:
        title = r.get('产品标题', '').strip()
        if not title or any(kw in title.lower() for kw in SKIP_ORDER_KW):
            continue
        key = (r['订单名称'], r['产品标题'], r['天'], r['净销售额'])
        if key in seen:
            continue
        seen.add(key)
        wi = date_to_week(r['天'].strip())
        if wi < 0:
            continue
        net = float(r['净销售额'].replace(',', ''))
        name = match_name(title)
        if name and name in needed:
            name_weekly_rev[name][wi] += net
            name_week_orders[name][wi][r['订单名称']] += net

    matched = 0
    for n in needed:
        p = products[n]
        if n in name_weekly_rev:
            p['weeklyRevenue'] = [round(x, 2) for x in name_weekly_rev[n]]
            p['revenue'] = round(sum(p['weeklyRevenue']), 2)
            woc = [0] * n_weeks
            for wi in range(n_weeks):
                woc[wi] = sum(1 for v in name_week_orders[n][wi].values() if v > 0)
            p['weeklyOrderCount'] = woc
            p['orderCount'] = sum(woc)
            matched += 1
        else:
            p['weeklyRevenue'] = [0] * n_weeks
            p['revenue'] = 0
            p['orderCount'] = 0
            p['weeklyOrderCount'] = [0] * n_weeks
        p['totalRevenue'] = p['revenue']

    print(f"  ✓ {matched} 个产品匹配到订单收入")


def step4_save_json(products, all_sorted, cat_products, needed, active_categories, prefixBench):
    """步骤4: 保存 JSON 数据文件"""
    print("💾 保存数据文件...")
    n_weeks = len(WEEKS)

    def to_dict(p):
        return {
            'name': p['name'], 'code': p['code'], 'firstChar': p['firstChar'], 'category': p['category'],
            'totalViews': p['totalViews'], 'users': p['totalUsers'],
            'carts': p['totalCarts'], 'checkouts': p['totalCheckouts'],
            'purchased': p['totalPurchased'], 'revenue': p.get('revenue', 0),
            'orderCount': p.get('orderCount', 0),
            'bounceRate': p['bounceRate'],
            'weeklyViews': p['weeklyViews'], 'weeklyUsers': p['weeklyUsers'],
            'weeklyCarts': p['weeklyCarts'], 'weeklyCheckouts': p['weeklyCheckouts'],
            'weeklyPurchased': p['weeklyPurchased'], 'weeklyRevenue': p.get('weeklyRevenue', [0] * n_weeks),
            'weeklyBounce': p['weeklyBounce'], 'weeklyOrderCount': p.get('weeklyOrderCount', [0] * n_weeks),
            'rank': p['rank'], 'ranks': p['ranks'],
            'catRank': p.get('catRank'), 'catRanks': p.get('catRanks', [None] * n_weeks),
            'rankDelta': p['rankDelta'], 'streak': p['streak'], 'bestRank': p['bestRank'],
            'trend': p['trend'], 'wow': p['wow'], 'tags': p['tags'],
            'prefixBench': p.get('prefixBench', 0), 'prefixTotal': p.get('prefixTotal', 0),
        }

    out_products = sorted([to_dict(products[n]) for n in needed], key=lambda x: x['rank'])

    categories_info = {}
    for cat in sorted(active_categories):
        cnt = len(cat_products[cat])
        categories_info[cat] = {'name': CAT_NAMES.get(cat, 'Other'), 'total': cnt, 'top50': min(cnt, 50)}

    all_wv = [sum(p['weeklyViews'][i] for p in products.values()) for i in range(n_weeks)]
    # All-products revenue from orders (sum from matched products is approximation)
    all_wr = [0.0] * n_weeks
    orders_file = find_orders_file()
    if orders_file:
        seen = set()
        with open(orders_file, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                title = r.get('产品标题', '').strip()
                if not title or any(kw in title.lower() for kw in SKIP_ORDER_KW): continue
                key = (r['订单名称'], r['产品标题'], r['天'], r['净销售额'])
                if key in seen: continue
                seen.add(key)
                wi = date_to_week(r['天'].strip())
                if wi < 0: continue
                all_wr[wi] += float(r['净销售额'].replace(',', ''))
    all_wr = [round(x, 2) for x in all_wr]

    top50_output = {
        'weeks': WEEK_NAMES,
        'products': out_products,
        'categories': categories_info,
        'summary': {'allWeeklyViews': all_wv, 'allWeeklyRevenue': all_wr},
        'prefixBench': prefixBench,
    }

    with open(os.path.join(BASE, 'top50_data.json'), 'w', encoding='utf-8') as f:
        json.dump(top50_output, f, ensure_ascii=False)
    print(f"  ✓ top50_data.json ({len(json.dumps(top50_output)):,} bytes)")

    # Category comparison data
    cat_output = []
    for cat in ['f', 'a', 't', 'h', 'p', 'v', 'l', 'b', 'm', 'd', 'other']:
        if cat not in cat_products: continue
        prods = cat_products[cat]
        c = {
            'key': cat, 'name': CAT_NAMES.get(cat, cat), 'productCount': len(prods),
            'totalViews': sum(p['totalViews'] for p in prods),
            'totalUsers': sum(p['totalUsers'] for p in prods),
            'totalCarts': sum(p['totalCarts'] for p in prods),
            'totalOrders': sum(p.get('orderCount', 0) for p in prods),
            'totalRevenue': round(sum(p.get('revenue', 0) for p in prods), 2),
            'weeklyViews': [sum(p['weeklyViews'][i] for p in prods) for i in range(n_weeks)],
            'weeklyUsers': [sum(p['weeklyUsers'][i] for p in prods) for i in range(n_weeks)],
            'weeklyCarts': [sum(p['weeklyCarts'][i] for p in prods) for i in range(n_weeks)],
            'weeklyOrders': [sum(p.get('weeklyOrderCount', [0] * n_weeks)[i] for p in prods) for i in range(n_weeks)],
            'weeklyRevenue': [round(sum(p.get('weeklyRevenue', [0] * n_weeks)[i] for p in prods), 2) for i in range(n_weeks)],
        }
        tv = c['totalViews']
        c['avgBounce'] = round(sum(p['bounceRate'] * p['totalViews'] for p in prods if p['totalViews'] > 0) / tv, 1) if tv > 0 else 0
        c['weeklyBounce'] = [0.0] * n_weeks
        for i in range(n_weeks):
            wv = sum(p['weeklyViews'][i] for p in prods)
            if wv > 0:
                c['weeklyBounce'][i] = round(sum(p['weeklyBounce'][i] * p['weeklyViews'][i] for p in prods) / wv, 1)
        c['avgEngTime'] = 0
        c['weeklyEngTime'] = [0] * n_weeks
        cat_output.append(c)

    cat_data = {
        'weeks': WEEK_NAMES,
        'categories': cat_output,
        'allWeeklyViews': all_wv,
        'allWeeklyRevenue': all_wr,
    }

    with open(os.path.join(BASE, 'category_data.json'), 'w', encoding='utf-8') as f:
        json.dump(cat_data, f, ensure_ascii=False)
    print(f"  ✓ category_data.json ({len(json.dumps(cat_data)):,} bytes)")

    return top50_output, cat_data


def step5_rebuild_dashboard(top50_output, cat_data):
    """步骤5: 重建合并看板 dashboard.html"""
    print("🔨 重建 dashboard.html...")

    top50_html_path = os.path.join(BASE, 'dashboard_top50.html')
    with open(top50_html_path, 'r', encoding='utf-8') as f:
        t = f.read()

    # Re-embed data into dashboard_top50.html first
    top50_json = json.dumps(top50_output, ensure_ascii=False)
    t = re.sub(r'window\.__EMBEDDED_DATA__\s*=\s*\{.*?\};',
               f'window.__EMBEDDED_DATA__ = {top50_json};', t, count=1, flags=re.DOTALL)
    with open(top50_html_path, 'w', encoding='utf-8') as f:
        f.write(t)

    # Extract parts
    css_s = t.index('<style>') + 7
    css_e = t.index('</style>')
    top50_css = t[css_s:css_e].replace('body {', '.x-ignore-body {')

    body_s = t.index('<body>') + 6
    body_e = t.index('</body>')
    body = t[body_s:body_e]

    data_tag_idx = body.index('<script id="embedded-data">')
    top50_body = body[:data_tag_idx].strip()

    m = re.search(r'window\.__EMBEDDED_DATA__\s*=\s*(\{.*?\});', body, re.DOTALL)
    top50_data_str = m.group(1)

    js_s = body.rindex('<script>') + 8
    js_e = body.rindex('</script>')
    top50_js = body[js_s:js_e].strip()

    cat_data_str = json.dumps(cat_data, ensure_ascii=False)

    # Read the build template
    template_path = os.path.join(BASE, 'dashboard_template.html')
    if not os.path.exists(template_path):
        # Build inline
        pass

    # Write merged dashboard.html using the same structure as before
    out_path = os.path.join(BASE, 'dashboard.html')
    with open(out_path, 'w', encoding='utf-8') as out:
        out.write('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n')
        out.write('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
        out.write('<title>LinkDolls 数据看板</title>\n<style>\n')
        out.write('* { margin:0; padding:0; box-sizing:border-box; }\n')
        out.write('body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; background:#f5f5f5; color:#333; display:flex; min-height:100vh; }\n')
        out.write('.sidebar { width:220px; background:#1e293b; color:white; flex-shrink:0; position:fixed; top:0; left:0; bottom:0; z-index:100; display:flex; flex-direction:column; }\n')
        out.write('.sidebar-logo { padding:24px 20px 20px; font-size:18px; font-weight:700; border-bottom:1px solid rgba(255,255,255,0.1); }\n')
        out.write('.sidebar-logo span { color:#60a5fa; }\n')
        out.write('.sidebar-nav { padding:12px 0; flex:1; }\n')
        out.write('.nav-section { padding:12px 20px 4px; font-size:10px; text-transform:uppercase; letter-spacing:1.5px; color:#64748b; font-weight:600; }\n')
        out.write('.nav-item { display:flex; align-items:center; gap:10px; padding:10px 20px; cursor:pointer; color:#94a3b8; font-size:14px; transition:all 0.15s; border-left:3px solid transparent; }\n')
        out.write('.nav-item:hover { background:rgba(255,255,255,0.05); color:#e2e8f0; }\n')
        out.write('.nav-item.active { background:rgba(59,130,246,0.15); color:#93c5fd; border-left-color:#3b82f6; font-weight:600; }\n')
        out.write('.nav-icon { font-size:18px; width:24px; text-align:center; }\n')
        out.write('.sidebar-footer { padding:16px 20px; font-size:11px; color:#475569; border-top:1px solid rgba(255,255,255,0.1); }\n')
        out.write('.main-content { margin-left:220px; flex:1; min-width:0; }\n')
        out.write('.page { display:none; }\n.page.active { display:block; }\n')
        out.write('#page-category .card { background:white; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,0.1); margin-bottom:20px; overflow:hidden; }\n')
        out.write('#page-category .card-title { padding:16px 20px; font-size:16px; font-weight:700; border-bottom:1px solid #f0f0f0; }\n')
        out.write('#page-category .cat-badge { display:inline-block; width:24px; height:24px; border-radius:50%; color:white; font-weight:700; font-size:12px; text-align:center; line-height:24px; margin-right:6px; }\n')
        out.write('#page-category .cat-name-col { font-weight:600; color:#1a1a1a; }\n')
        out.write('#page-category .bar-cell { min-width:120px; }\n')
        out.write('#page-category .bar-bg { height:8px; background:#e5e7eb; border-radius:4px; overflow:hidden; margin-top:2px; }\n')
        out.write('#page-category .bar-fill { height:100%; border-radius:4px; transition:width 0.3s; }\n')
        out.write('#page-category .cat-sparkline { width:100px; height:28px; }\n')
        out.write('#page-category .totals-row td { font-weight:700; background:#f8fafc; border-top:2px solid #e5e7eb; }\n')
        out.write('#page-category .cat-filters { background:white; padding:16px 24px; border-radius:8px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,0.1); display:flex; gap:20px; align-items:center; }\n')
        out.write('#page-category .cat-filter-label { font-size:12px; color:#888; margin-bottom:4px; }\n')
        out.write('#page-category table { width:100%; border-collapse:collapse; font-size:13px; }\n')
        out.write('#page-category th { background:#fafafa; padding:10px 14px; text-align:right; font-weight:600; color:#666; border-bottom:2px solid #e5e7eb; white-space:nowrap; }\n')
        out.write('#page-category th:first-child, #page-category th:nth-child(2) { text-align:left; }\n')
        out.write('#page-category td { padding:10px 14px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap; }\n')
        out.write('#page-category td:first-child, #page-category td:nth-child(2) { text-align:left; }\n')
        out.write('#page-category tr:hover { background:#f8fafc; }\n')
        out.write(top50_css)
        out.write('\n</style>\n</head>\n<body>\n')

        # Sidebar
        out.write('<div class="sidebar">\n<div class="sidebar-logo"><span>LinkDolls</span> 看板</div>\n<div class="sidebar-nav">\n')
        out.write('<div class="nav-section">详情页 PDP</div>\n')
        out.write('<div class="nav-item active" data-page="top50"><span class="nav-icon">📊</span><span>Top 50 趋势</span></div>\n')
        out.write('<div class="nav-item" data-page="category"><span class="nav-icon">📋</span><span>类别横向对比</span></div>\n')
        out.write('<div class="nav-section">分类页</div>\n')
        out.write('<a class="nav-item" href="dashboard_collection.html" style="text-decoration:none;"><span class="nav-icon">📈</span><span>分类页数据看板</span></a>\n')
        out.write('</div>\n<div class="sidebar-footer">W10–W16 数据</div>\n</div>\n')

        # Main content
        out.write('<div class="main-content">\n')
        out.write(f'<div class="page active" id="page-top50">\n{top50_body}\n</div>\n')

        # Category page
        out.write('<div class="page" id="page-category">\n')
        out.write('<div class="container"><div class="header"><div class="header-title">产品类别横向对比</div>')
        out.write('<div class="header-subtitle">W10–W16 · 按产品首字母分类对比核心指标</div></div>\n')
        out.write('<div class="cat-filters"><div><div class="cat-filter-label">查看周</div>')
        out.write('<select class="filter-select" id="catWeekSelector" style="font-weight:700;color:#2563eb;"><option value="all">全部 7 周汇总</option></select></div>\n')
        out.write('<div><div class="cat-filter-label">排序</div><select class="filter-select" id="catSortSelector">')
        out.write('<option value="views">按浏览量</option><option value="revenue">按收入</option>')
        out.write('<option value="cartRate">按加购率</option><option value="convRate">按转化率</option>')
        out.write('<option value="avgViews">按人均浏览</option><option value="count">按产品数</option>')
        out.write('</select></div></div>\n')
        out.write('<div class="card"><div class="card-title" id="catTableTitle">类别横向对比</div>')
        out.write('<div class="table-scroll"><table><thead><tr id="catTableHead"></tr></thead><tbody id="catTableBody"></tbody></table></div></div>\n')
        out.write('</div></div>\n')

        out.write('</div>\n')  # close main-content

        # Data
        out.write(f'<script>window.__EMBEDDED_DATA__ = {top50_data_str};</script>\n')
        out.write(f'<script>window.__CAT_DATA__ = {cat_data_str};</script>\n')

        # Nav JS
        out.write('<script>\n')
        out.write("document.querySelectorAll('.nav-item').forEach(function(item) {\n")
        out.write("  item.addEventListener('click', function() {\n")
        out.write("    document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });\n")
        out.write("    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });\n")
        out.write("    item.classList.add('active');\n")
        out.write("    document.getElementById('page-' + item.dataset.page).classList.add('active');\n")
        out.write("  });\n});\n</script>\n")

        # Top50 JS
        out.write(f'<script>\n(function() {{\n{top50_js}\n}})();\n</script>\n')

        # Category JS (inline)
        cat_js_file = os.path.join(BASE, 'category_render.js')
        cat_js = _build_category_js()
        out.write(f'<script>\n{cat_js}\n</script>\n')

        out.write('</body>\n</html>')

    size = os.path.getsize(out_path)
    print(f"  ✓ dashboard.html ({size:,} bytes)")


def _build_category_js():
    """生成类别对比页面的 JS"""
    return r"""
(function() {
    var cd = window.__CAT_DATA__;
    var catColors = {'f':'#dc2626','a':'#ea580c','t':'#d97706','h':'#0891b2','p':'#7c3aed','v':'#65a30d','l':'#16a34a','b':'#ec4899','m':'#059669','d':'#0284c7','other':'#6b7280'};
    var csw = -1;
    (function() {
        var sel = document.getElementById('catWeekSelector');
        cd.weeks.forEach(function(w,i) {
            var o = document.createElement('option');
            o.value = i; o.textContent = w + (i===cd.weeks.length-1?' (最新)':'');
            sel.appendChild(o);
        });
    })();
    function fm(v) { return '$'+v.toLocaleString('en-US',{maximumFractionDigits:0}); }
    function fe(s) { return Math.floor(s/60)+'m '+Math.floor(s%60)+'s'; }
    function spark(cv,vals,color) {
        var ctx=cv.getContext('2d'),W=cv.width,H=cv.height;
        if(!vals||!vals.length)return;
        var mx=Math.max.apply(null,vals.concat([1]));
        ctx.fillStyle='#f0f0f0';ctx.fillRect(0,0,W,H);
        ctx.strokeStyle=color;ctx.lineWidth=2;ctx.globalAlpha=0.8;ctx.beginPath();
        vals.forEach(function(v,i){var x=i/(vals.length-1)*(W-8)+4,y=H-4-(v/mx)*(H-8);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);});
        ctx.stroke();var lx=W-4,ly=H-4-(vals[vals.length-1]/mx)*(H-8);
        ctx.beginPath();ctx.arc(lx,ly,3,0,Math.PI*2);ctx.fillStyle=color;ctx.globalAlpha=1;ctx.fill();
    }
    function render() {
        var w=csw,isAll=w===-1,label=isAll?'7 周汇总':cd.weeks[w];
        document.getElementById('catTableTitle').textContent='类别横向对比 · '+label;
        document.getElementById('catTableHead').innerHTML='<th>类别</th><th>名称</th><th>产品数</th><th>浏览量</th><th>浏览占比</th><th>7周走势</th><th>活跃用户</th><th>人均浏览</th><th>环比</th><th>加购数</th><th>加购率</th><th>订单数</th><th>转化率</th><th>收入</th><th>收入占比</th><th>跳出率</th>';
        var rows=cd.categories.map(function(c){
            var vi,us,ca,od,rv,bo,wow;
            if(isAll){vi=c.totalViews;us=c.totalUsers;ca=c.totalCarts;od=c.totalOrders;rv=c.totalRevenue;bo=c.avgBounce;var v6=c.weeklyViews[6],v5=c.weeklyViews[5];wow=v5>0?((v6-v5)/v5*100).toFixed(1):'—';}
            else{vi=c.weeklyViews[w];us=c.weeklyUsers[w];ca=c.weeklyCarts[w];od=c.weeklyOrders[w];rv=c.weeklyRevenue[w];bo=c.weeklyBounce[w];wow=(w>0&&c.weeklyViews[w-1]>0)?((vi-c.weeklyViews[w-1])/c.weeklyViews[w-1]*100).toFixed(1):'—';}
            return Object.assign({},c,{vi:vi,us:us,ca:ca,od:od,rv:rv,bo:bo,wow:wow,cr:vi>0?(ca/vi*100).toFixed(2):'0',cv:vi>0?(od/vi*100).toFixed(3):'0',av:c.productCount>0?(vi/c.productCount).toFixed(1):'0'});
        });
        var sb=document.getElementById('catSortSelector').value;
        var sf={views:function(a,b){return b.vi-a.vi},revenue:function(a,b){return b.rv-a.rv},cartRate:function(a,b){return parseFloat(b.cr)-parseFloat(a.cr)},convRate:function(a,b){return parseFloat(b.cv)-parseFloat(a.cv)},avgViews:function(a,b){return parseFloat(b.av)-parseFloat(a.av)},count:function(a,b){return b.productCount-a.productCount}};
        rows.sort(sf[sb]||sf.views);
        var tv=rows.reduce(function(s,r){return s+r.vi},0),tr=rows.reduce(function(s,r){return s+r.rv},0);
        var tb=document.getElementById('catTableBody');tb.innerHTML='';
        rows.forEach(function(r){
            var vp=tv>0?(r.vi/tv*100).toFixed(1):'0',rp=tr>0?(r.rv/tr*100).toFixed(1):'0';
            var co=catColors[r.key]||'#6b7280';
            var wc=r.wow!=='—'?(parseFloat(r.wow)>=0?'wow-positive':'wow-negative'):'';
            var wt=r.wow!=='—'?(parseFloat(r.wow)>0?'+'+r.wow+'%':r.wow+'%'):'—';
            var tr2=document.createElement('tr');
            tr2.innerHTML='<td><span class="cat-badge" style="background:'+co+'">'+(r.key==='other'?'?':r.key.toUpperCase())+'</span></td><td class="cat-name-col">'+r.name+'</td><td>'+r.productCount.toLocaleString()+'</td><td style="font-weight:700">'+r.vi.toLocaleString()+'</td><td class="bar-cell"><span>'+vp+'%</span><div class="bar-bg"><div class="bar-fill" style="width:'+vp+'%;background:'+co+';"></div></div></td><td><canvas class="cat-sparkline" data-v=\''+JSON.stringify(r.weeklyViews)+'\' data-c=\''+co+'\'></canvas></td><td>'+r.us.toLocaleString()+'</td><td>'+r.av+'</td><td><span class="'+wc+'">'+wt+'</span></td><td>'+r.ca+'</td><td>'+r.cr+'%</td><td>'+r.od+'</td><td>'+r.cv+'%</td><td style="font-weight:600">'+fm(r.rv)+'</td><td class="bar-cell"><span>'+rp+'%</span><div class="bar-bg"><div class="bar-fill" style="width:'+rp+'%;background:#059669;"></div></div></td><td>'+r.bo.toFixed(1)+'%</td>';
            tb.appendChild(tr2);
        });
        var tc=rows.reduce(function(s,r){return s+r.ca},0),to=rows.reduce(function(s,r){return s+r.od},0);
        var tu=rows.reduce(function(s,r){return s+r.us},0),tn=rows.reduce(function(s,r){return s+r.productCount},0);
        var tt=document.createElement('tr');tt.className='totals-row';
        tt.innerHTML='<td></td><td class="cat-name-col">合计</td><td>'+tn.toLocaleString()+'</td><td>'+tv.toLocaleString()+'</td><td>100%</td><td></td><td>'+tu.toLocaleString()+'</td><td>'+(tv/tn).toFixed(1)+'</td><td></td><td>'+tc+'</td><td>'+(tv>0?(tc/tv*100).toFixed(2):'0')+'%</td><td>'+to+'</td><td>'+(tv>0?(to/tv*100).toFixed(3):'0')+'%</td><td style="font-weight:700">'+fm(tr)+'</td><td>100%</td><td></td>';
        tb.appendChild(tt);
        document.querySelectorAll('canvas.cat-sparkline').forEach(function(c){spark(c,JSON.parse(c.getAttribute('data-v')),c.getAttribute('data-c'));});
    }
    document.getElementById('catWeekSelector').addEventListener('change',function(){csw=this.value==='all'?-1:parseInt(this.value);render();});
    document.getElementById('catSortSelector').addEventListener('change',render);
    render();
})();
"""


def main():
    print("=" * 60)
    print("LinkDolls PDP 看板数据更新")
    print("=" * 60)

    products = step1_read_ecommerce()
    all_sorted, cat_products, needed, active_cats, prefixBench = step2_classify_and_rank(products)
    step3_match_orders(products, needed)
    top50_output, cat_data = step4_save_json(products, all_sorted, cat_products, needed, active_cats, prefixBench)
    step5_rebuild_dashboard(top50_output, cat_data)

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
