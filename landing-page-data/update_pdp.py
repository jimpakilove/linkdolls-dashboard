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
from difflib import SequenceMatcher  # noqa: F401 – kept for compatibility

# ── 字段映射（兼容中英文表头 + BOM） ──
_ORDER_FIELD_MAP = {
    '产品标题': 'Product title',
    '订单名称': 'Order name',
    '天': 'Day',
    '净销售额': 'Net sales',
}
_field_cache = {}

def get_field(row, key):
    """从 DictReader row 中读取字段，兼容中英文表头。"""
    rid = id(row)
    if rid not in _field_cache:
        _field_cache[rid] = {k.strip().strip('\ufeff').lower(): k for k in row.keys()}
    norm = _field_cache[rid]
    # 尝试直接匹配（中文键或英文键）
    for k in (key, _ORDER_FIELD_MAP.get(key, key)):
        if k in row:
            return row[k]
        kl = k.strip().strip('\ufeff').lower()
        if kl in norm:
            return row[norm[kl]]
    return row.get(key)

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


def normalize_date(d):
    """统一日期格式：2026/4/29 -> 2026-04-29"""
    if '/' in d:
        parts = d.split('/')
        if len(parts) == 3:
            return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return d


def date_to_week(d):
    """日期字符串 -> 周索引，不在范围内返回 -1"""
    d = normalize_date(d)
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
    """步骤1: 读取电子商务购买数据（按产品代码聚合变体）"""
    print("📦 读取电子商务购买数据...")
    n_weeks = len(WEEKS)
    raw_products = {}

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
            # 提取产品代码
            code, cat, first = get_code_and_cat(name)
            if not code:
                code = name  # fallback: 无代码的产品用名称作为key

            if code not in raw_products:
                raw_products[code] = {
                    'names': [],  # 收集所有变体名称
                    'code': code,
                    'category': cat,
                    'firstChar': first,
                    'weeklyViews': [0] * n_weeks, 'weeklyUsers': [0] * n_weeks,
                    'weeklyCarts': [0] * n_weeks, 'weeklyPurchased': [0] * n_weeks,
                    'weeklyRevenue': [0.0] * n_weeks, 'weeklyBounce': [0.0] * n_weeks,
                    'weeklyCheckouts': [0] * n_weeks,
                    'weeklyBounceWeight': [0] * n_weeks,  # 用于加权平均跳出率
                }

            p = raw_products[code]
            p['names'].append(name)

            views = int(row.get('查看过的商品数', 0))
            p['weeklyViews'][wi] += views
            p['weeklyUsers'][wi] += int(row.get('活跃用户', 0))
            p['weeklyCarts'][wi] += int(row.get('加入购物车的商品数', 0))
            p['weeklyPurchased'][wi] += int(row.get('已购买的商品数', 0))
            p['weeklyRevenue'][wi] += float(row.get('商品收入', 0))
            p['weeklyCheckouts'][wi] += int(row.get('结账的商品数', 0))
            # 跳出率加权累加
            p['weeklyBounce'][wi] += round(float(row.get('跳出率', 0)) * 100, 1) * views
            p['weeklyBounceWeight'][wi] += views
            count += 1
        print(f"  ✓ {wname}: {count} 产品")

    # 转换为最终产品格式
    products = {}
    for code, p in raw_products.items():
        # 计算加权平均跳出率
        for wi in range(n_weeks):
            if p['weeklyBounceWeight'][wi] > 0:
                p['weeklyBounce'][wi] = round(p['weeklyBounce'][wi] / p['weeklyBounceWeight'][wi], 1)
            else:
                p['weeklyBounce'][wi] = 0.0

        # 选择最佳名称：保留最长名称（通常最完整）
        all_names = list(set(p['names']))
        best_name = max(all_names, key=len) if all_names else code

        # 清理临时字段
        del p['names']
        del p['weeklyBounceWeight']

        products[code] = p
        products[code]['name'] = best_name

    print(f"  原始产品: {count} 个, 聚合后: {len(products)} 个唯一产品")
    return products


def step2_classify_and_rank(products):
    """步骤2: 分类、计算聚合指标、排名"""
    print("📊 计算排名和趋势...")
    n_weeks = len(WEEKS)

    for code, p in products.items():
        # code, cat, first 已经在 step1 中设置
        cat = p['category']
        first = p['firstChar']
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
    needed = set(p['code'] for p in all_sorted[:50])
    active_categories = []
    for cat, prods in cat_products.items():
        if len(prods) >= 3:
            active_categories.append(cat)
            for p in prods[:50]:
                needed.add(p['code'])

    print(f"  ✓ 总榜 Top50 + {len(active_categories)} 个类别 = {len(needed)} 个产品")
    return all_sorted, cat_products, needed, active_categories, prefixBench


def step3_match_orders(products, needed):
    """步骤3: 匹配订单收入（按产品代码聚合）"""
    orders_file = find_orders_file()
    if not orders_file:
        return

    print(f"💰 匹配订单收入: {os.path.basename(orders_file)}")
    n_weeks = len(WEEKS)

    def extract_code(title):
        m = re.match(r'^([A-Za-z]\d+)', title.strip())
        return m.group(1).lower() if m else None

    def match_code(order_title):
        return extract_code(order_title)

    with open(orders_file, 'r', encoding='utf-8-sig') as f:
        raw_rows = list(csv.DictReader(f))

    seen = set()
    code_weekly_rev = defaultdict(lambda: [0.0] * n_weeks)
    code_week_orders = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    for r in raw_rows:
        title = get_field(r, '产品标题')
        title = title.strip() if title else ''
        if not title or any(kw in title.lower() for kw in SKIP_ORDER_KW):
            continue
        key = (get_field(r, '订单名称'), get_field(r, '产品标题'), get_field(r, '天'), get_field(r, '净销售额'))
        if key in seen:
            continue
        seen.add(key)
        wi = date_to_week(get_field(r, '天').strip())
        if wi < 0:
            continue
        net = float(get_field(r, '净销售额').replace(',', ''))
        code = match_code(title)
        if code and code in needed:
            code_weekly_rev[code][wi] += net
            code_week_orders[code][wi][get_field(r, '订单名称')] += net

    matched = 0
    for code in needed:
        p = products[code]
        if code in code_weekly_rev:
            p['weeklyRevenue'] = [round(x, 2) for x in code_weekly_rev[code]]
            p['revenue'] = round(sum(p['weeklyRevenue']), 2)
            woc = [0] * n_weeks
            for wi in range(n_weeks):
                woc[wi] = sum(1 for v in code_week_orders[code][wi].values() if v > 0)
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


def step3b_category_revenue(orders_file, week_starts=None, week_end=None,
                             n_weeks=None, skip_kw=None, cat_names=None):
    """步骤3b: 直接按产品首字母从订单 CSV 汇总分类收入（不依赖产品匹配）。

    参数默认从模块全局变量读取，可通过关键字参数覆盖（便于测试）。

    返回:
        dict[cat_key] → {
            'weeklyRevenue': [float, ...],   # 每周净销售额
            'weeklyOrders':  [int,   ...],   # 每周订单数（去重）
            'totalRevenue':  float,
            'totalOrders':   int,
        }
    """
    _week_starts = week_starts if week_starts is not None else WEEK_STARTS
    _week_end    = week_end    if week_end    is not None else WEEK_END
    _n_weeks     = n_weeks     if n_weeks     is not None else len(WEEKS)
    _skip_kw     = skip_kw     if skip_kw     is not None else SKIP_ORDER_KW
    _cat_names   = cat_names   if cat_names   is not None else CAT_NAMES

    def _date_to_week(d):
        if d < _week_starts[0] or d >= _week_end:
            return -1
        for i in range(len(_week_starts) - 1, -1, -1):
            if d >= _week_starts[i]:
                return i
        return -1

    result = {}
    for cat in list(_cat_names.keys()):
        result[cat] = {
            'weeklyRevenue': [0.0] * _n_weeks,
            'weeklyOrders':  [0]   * _n_weeks,
            'totalRevenue':  0.0,
            'totalOrders':   0,
        }

    seen = set()
    with open(orders_file, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            title = get_field(r, '产品标题')
            title = title.strip() if title else ''
            if not title:
                continue
            if any(kw in title.lower() for kw in _skip_kw):
                continue

            # 去重：同一订单+产品+日期+金额只算一次
            day = get_field(r, '天')
            day = day.strip() if day else ''
            net_str = get_field(r, '净销售额')
            net_str = net_str.strip().replace(',', '') if net_str else '0'
            key = (get_field(r, '订单名称'), title, day, net_str)
            if key in seen:
                continue
            seen.add(key)

            wi = _date_to_week(day)
            if wi < 0:
                continue

            try:
                net = float(net_str)
            except ValueError:
                continue

            # 按首字母归分类
            first = title[0].lower()
            cat = first if first in _cat_names else 'other'

            result[cat]['weeklyRevenue'][wi] += net
            result[cat]['weeklyOrders'][wi]  += 1

    # 汇总合计
    for cat in result:
        result[cat]['weeklyRevenue'] = [round(v, 2) for v in result[cat]['weeklyRevenue']]
        result[cat]['totalRevenue']  = round(sum(result[cat]['weeklyRevenue']), 2)
        result[cat]['totalOrders']   = sum(result[cat]['weeklyOrders'])

    return result


def step4_save_json(products, all_sorted, cat_products, needed, active_categories, prefixBench,
                    cat_revenue=None):
    """步骤4: 保存 JSON 数据文件。
    cat_revenue: step3b_category_revenue() 的返回值，用于覆盖分类级收入数据。
    """
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
                title = get_field(r, '产品标题')
                title = title.strip() if title else ''
                if not title or any(kw in title.lower() for kw in SKIP_ORDER_KW): continue
                key = (get_field(r, '订单名称'), get_field(r, '产品标题'), get_field(r, '天'), get_field(r, '净销售额'))
                if key in seen: continue
                seen.add(key)
                wi = date_to_week(get_field(r, '天').strip())
                if wi < 0: continue
                all_wr[wi] += float(get_field(r, '净销售额').replace(',', ''))
    all_wr = [round(x, 2) for x in all_wr]

    top50_output = {
        'weeks': WEEK_NAMES,
        'weekStarts': WEEK_STARTS,
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
            # 收入/订单数：优先用 step3b 按首字母直接汇总的数据，产品级加总仅作回退
            'totalOrders': (cat_revenue[cat]['totalOrders']
                            if cat_revenue and cat in cat_revenue
                            else sum(p.get('orderCount', 0) for p in prods)),
            'totalRevenue': (cat_revenue[cat]['totalRevenue']
                             if cat_revenue and cat in cat_revenue
                             else round(sum(p.get('revenue', 0) for p in prods), 2)),
            'weeklyViews': [sum(p['weeklyViews'][i] for p in prods) for i in range(n_weeks)],
            'weeklyUsers': [sum(p['weeklyUsers'][i] for p in prods) for i in range(n_weeks)],
            'weeklyCarts': [sum(p['weeklyCarts'][i] for p in prods) for i in range(n_weeks)],
            'weeklyOrders': (cat_revenue[cat]['weeklyOrders']
                             if cat_revenue and cat in cat_revenue
                             else [sum(p.get('weeklyOrderCount', [0] * n_weeks)[i] for p in prods) for i in range(n_weeks)]),
            'weeklyRevenue': (cat_revenue[cat]['weeklyRevenue']
                              if cat_revenue and cat in cat_revenue
                              else [round(sum(p.get('weeklyRevenue', [0] * n_weeks)[i] for p in prods), 2) for i in range(n_weeks)]),
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
        'weekStarts': WEEK_STARTS,
        'categories': cat_output,
        'allWeeklyViews': all_wv,
        'allWeeklyRevenue': all_wr,
    }

    with open(os.path.join(BASE, 'category_data.json'), 'w', encoding='utf-8') as f:
        json.dump(cat_data, f, ensure_ascii=False)
    print(f"  ✓ category_data.json ({len(json.dumps(cat_data)):,} bytes)")

    return top50_output, cat_data


def step5_rebuild_dashboard(top50_output, cat_data):
    """步骤5: 重建合并看板 dashboard.html

    使用现有的 dashboard.html 作为模板，只替换数据注入部分，
    保留所有前端功能（包括4周粒度切换等）。
    """
    print("🔨 重建 dashboard.html...")

    out_path = os.path.join(BASE, 'dashboard.html')

    # 1. 尝试读取现有的 dashboard.html 作为模板
    template_path = os.path.join(BASE, 'dashboard.html')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        # fallback: 读取 dashboard_top50.html
        top50_html_path = os.path.join(BASE, 'dashboard_top50.html')
        with open(top50_html_path, 'r', encoding='utf-8') as f:
            html = f.read()

    top50_json = json.dumps(top50_output, ensure_ascii=False)
    cat_json = json.dumps(cat_data, ensure_ascii=False)

    # 2. 替换数据注入部分
    html = re.sub(
        r'<script>window\.__EMBEDDED_DATA__\s*=\s*\{.*?\};</script>',
        f'<script>window.__EMBEDDED_DATA__ = {top50_json};</script>',
        html, count=1, flags=re.DOTALL
    )
    html = re.sub(
        r'<script>window\.__CAT_DATA__\s*=\s*\{.*?\};</script>',
        f'<script>window.__CAT_DATA__ = {cat_json};</script>',
        html, count=1, flags=re.DOTALL
    )

    # 3. 写入输出
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size = os.path.getsize(out_path)
    print(f"  ✓ dashboard.html ({size:,} bytes)")


def _build_category_js():
    """生成类别对比页面的 JS（支持周/4周双时间颗粒度）"""
    return r"""
(function() {
    var cd = window.__CAT_DATA__;
    var catColors = {'f':'#dc2626','a':'#ea580c','t':'#d97706','h':'#0891b2','p':'#7c3aed','v':'#65a30d','l':'#16a34a','b':'#ec4899','m':'#059669','d':'#0284c7','other':'#6b7280'};
    var granularity = 'week'; // 'week' or '4week'
    var csw = -1;

    // Build 4-week periods from weekStarts
    var periods4w = [];
    if (cd.weekStarts) {
        var ws = cd.weekStarts;
        for (var i = 0; i < cd.weeks.length; i += 4) {
            var endIdx = Math.min(i + 3, cd.weeks.length - 1);
            var sDate = ws[i].replace(/^\d{4}-/, '').replace(/-/g, '/');
            var eDate = ws[endIdx].replace(/^\d{4}-/, '').replace(/-/g, '/');
            // end date = start of last week + 6 days
            var eParts = ws[endIdx].split('-');
            var eDt = new Date(parseInt(eParts[0]), parseInt(eParts[1])-1, parseInt(eParts[2]));
            eDt.setDate(eDt.getDate() + 6);
            eDate = (eDt.getMonth()+1) + '/' + eDt.getDate();
            var weekCount = endIdx - i + 1;
            var isFull = weekCount === 4;
            var label = cd.weeks[i] + '–' + cd.weeks[endIdx] + ' · ' + sDate + '–' + eDate;
            if (!isFull) label += ' (不足4周)';
            periods4w.push({ label: label, startIdx: i, endIdx: endIdx, weekCount: weekCount, isFull: isFull });
        }
    }

    // Aggregate category data for a set of week indices
    function aggWeeks(c, indices) {
        var vi=0,us=0,ca=0,od=0,rv=0,boSum=0,boW=0;
        indices.forEach(function(i){
            vi += c.weeklyViews[i]||0;
            us += c.weeklyUsers[i]||0;
            ca += c.weeklyCarts[i]||0;
            od += c.weeklyOrders[i]||0;
            rv += c.weeklyRevenue[i]||0;
            var bw = c.weeklyViews[i]||0;
            if(bw>0){boSum += (c.weeklyBounce[i]||0)*bw; boW += bw;}
        });
        return {vi:vi,us:us,ca:ca,od:od,rv:rv,bo:boW>0?boSum/boW:0};
    }

    function populateSelector() {
        var sel = document.getElementById('catWeekSelector');
        sel.innerHTML = '';
        if (granularity === 'week') {
            var oAll = document.createElement('option');
            oAll.value = 'all'; oAll.textContent = '全部 ' + cd.weeks.length + ' 周汇总';
            sel.appendChild(oAll);
            cd.weeks.forEach(function(w, i) {
                var o = document.createElement('option');
                o.value = i; o.textContent = w + (i === cd.weeks.length - 1 ? ' (最新)' : '');
                sel.appendChild(o);
            });
        } else {
            var oAll = document.createElement('option');
            oAll.value = 'all'; oAll.textContent = '全部周期汇总';
            sel.appendChild(oAll);
            periods4w.forEach(function(p, i) {
                var o = document.createElement('option');
                o.value = i; o.textContent = p.label + (i === periods4w.length - 1 ? ' (最新)' : '');
                sel.appendChild(o);
            });
        }
        csw = -1;
        sel.value = 'all';
    }

    function fm(v) { return '$'+v.toLocaleString('en-US',{maximumFractionDigits:0}); }
    function spark(cv,vals,color) {
        var ctx=cv.getContext('2d'),W=cv.width,H=cv.height;
        if(!vals||!vals.length)return;
        var mx=Math.max.apply(null,vals.concat([1]));
        ctx.fillStyle='#f0f0f0';ctx.fillRect(0,0,W,H);
        ctx.strokeStyle=color;ctx.lineWidth=2;ctx.globalAlpha=0.8;ctx.beginPath();
        vals.forEach(function(v,i){var x=vals.length===1?W/2:i/(vals.length-1)*(W-8)+4,y=H-4-(v/mx)*(H-8);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);});
        ctx.stroke();var lx=vals.length===1?W/2:W-4,ly=H-4-(vals[vals.length-1]/mx)*(H-8);
        ctx.beginPath();ctx.arc(lx,ly,3,0,Math.PI*2);ctx.fillStyle=color;ctx.globalAlpha=1;ctx.fill();
    }

    function render() {
        var isAll = csw === -1;
        var label, trendLabel, sparkData, rows;

        if (granularity === 'week') {
            label = isAll ? (cd.weeks.length + ' 周汇总') : cd.weeks[csw];
            trendLabel = cd.weeks.length + '周走势';
            document.getElementById('catTableTitle').textContent = '类别横向对比 · ' + label;
            document.getElementById('catTableHead').innerHTML = '<th>类别</th><th>名称</th><th>产品数</th><th>浏览量</th><th>浏览占比</th><th>'+trendLabel+'</th><th>活跃用户</th><th>人均浏览</th><th>环比</th><th>加购数</th><th>加购率</th><th>订单数</th><th>转化率</th><th>收入</th><th>收入占比</th><th>跳出率</th>';
            rows = cd.categories.map(function(c) {
                var vi,us,ca,od,rv,bo,wow;
                if(isAll){vi=c.totalViews;us=c.totalUsers;ca=c.totalCarts;od=c.totalOrders;rv=c.totalRevenue;bo=c.avgBounce;var v6=c.weeklyViews[cd.weeks.length-1],v5=c.weeklyViews[cd.weeks.length-2];wow=v5>0?((v6-v5)/v5*100).toFixed(1):'—';}
                else{vi=c.weeklyViews[csw];us=c.weeklyUsers[csw];ca=c.weeklyCarts[csw];od=c.weeklyOrders[csw];rv=c.weeklyRevenue[csw];bo=c.weeklyBounce[csw];wow=(csw>0&&c.weeklyViews[csw-1]>0)?((vi-c.weeklyViews[csw-1])/c.weeklyViews[csw-1]*100).toFixed(1):'—';}
                return Object.assign({},c,{vi:vi,us:us,ca:ca,od:od,rv:rv,bo:bo,wow:wow,cr:vi>0?(ca/vi*100).toFixed(2):'0',cv:vi>0?(od/vi*100).toFixed(3):'0',av:c.productCount>0?(vi/c.productCount).toFixed(1):'0',sparkVals:c.weeklyViews});
            });
        } else {
            // 4-week mode
            if (isAll) {
                label = '全部周期汇总';
                trendLabel = periods4w.length + '周期走势';
                document.getElementById('catTableTitle').textContent = '类别横向对比 · ' + label;
                document.getElementById('catTableHead').innerHTML = '<th>类别</th><th>名称</th><th>产品数</th><th>浏览量</th><th>浏览占比</th><th>'+trendLabel+'</th><th>活跃用户</th><th>人均浏览</th><th>环比</th><th>加购数</th><th>加购率</th><th>订单数</th><th>转化率</th><th>收入</th><th>收入占比</th><th>跳出率</th>';
                rows = cd.categories.map(function(c) {
                    var totals = {vi:0,us:0,ca:0,od:0,rv:0,bo:0,boW:0};
                    var pSpark = [];
                    periods4w.forEach(function(p) {
                        var a = aggWeeks(c, function(){var a=[];for(var j=p.startIdx;j<=p.endIdx;j++)a.push(j);return a}());
                        totals.vi+=a.vi; totals.us+=a.us; totals.ca+=a.ca; totals.od+=a.od; totals.rv+=a.rv;
                        totals.boSum=(totals.boSum||0)+a.bo*a.vi; totals.boW=(totals.boW||0)+a.vi;
                        pSpark.push(a.vi);
                    });
                    var lastP = pSpark[pSpark.length-1], prevP = pSpark.length>1?pSpark[pSpark.length-2]:0;
                    var wow = prevP>0?((lastP-prevP)/prevP*100).toFixed(1):'—';
                    return Object.assign({},c,{vi:totals.vi,us:totals.us,ca:totals.ca,od:totals.od,rv:totals.rv,bo:totals.boW>0?totals.boSum/totals.boW:0,wow:wow,cr:totals.vi>0?(totals.ca/totals.vi*100).toFixed(2):'0',cv:totals.vi>0?(totals.od/totals.vi*100).toFixed(3):'0',av:c.productCount>0?(totals.vi/c.productCount).toFixed(1):'0',sparkVals:pSpark});
                });
            } else {
                var p = periods4w[csw];
                label = p.label;
                trendLabel = periods4w.length + '周期走势';
                document.getElementById('catTableTitle').textContent = '类别横向对比 · ' + label;
                document.getElementById('catTableHead').innerHTML = '<th>类别</th><th>名称</th><th>产品数</th><th>浏览量</th><th>浏览占比</th><th>'+trendLabel+'</th><th>活跃用户</th><th>人均浏览</th><th>环比</th><th>加购数</th><th>加购率</th><th>订单数</th><th>转化率</th><th>收入</th><th>收入占比</th><th>跳出率</th>';
                var indices = []; for(var j=p.startIdx;j<=p.endIdx;j++) indices.push(j);
                rows = cd.categories.map(function(c) {
                    var a = aggWeeks(c, indices);
                    var sparkVals = [];
                    periods4w.forEach(function(pp) {
                        var ii=[];for(var k=pp.startIdx;k<=pp.endIdx;k++)ii.push(k);
                        sparkVals.push(aggWeeks(c,ii).vi);
                    });
                    var wow = csw>0 ? (function(){var pp=periods4w[csw-1];var ii=[];for(var k=pp.startIdx;k<=pp.endIdx;k++)ii.push(k);var prev=aggWeeks(c,ii);return prev.vi>0?((a.vi-prev.vi)/prev.vi*100).toFixed(1):'—';})() : '—';
                    return Object.assign({},c,{vi:a.vi,us:a.us,ca:a.ca,od:a.od,rv:a.rv,bo:a.bo,wow:wow,cr:a.vi>0?(a.ca/a.vi*100).toFixed(2):'0',cv:a.vi>0?(a.od/a.vi*100).toFixed(3):'0',av:c.productCount>0?(a.vi/c.productCount).toFixed(1):'0',sparkVals:sparkVals});
                });
            }
        }

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
            tr2.innerHTML='<td><span class="cat-badge" style="background:'+co+'">'+(r.key==='other'?'?':r.key.toUpperCase())+'</span></td><td class="cat-name-col">'+r.name+'</td><td>'+r.productCount.toLocaleString()+'</td><td style="font-weight:700">'+r.vi.toLocaleString()+'</td><td class="bar-cell"><span>'+vp+'%</span><div class="bar-bg"><div class="bar-fill" style="width:'+vp+'%;background:'+co+';"></div></div></td><td><canvas class="cat-sparkline" data-v=\''+JSON.stringify(r.sparkVals)+'\' data-c=\''+co+'\'></canvas></td><td>'+r.us.toLocaleString()+'</td><td>'+r.av+'</td><td><span class="'+wc+'">'+wt+'</span></td><td>'+r.ca+'</td><td>'+r.cr+'%</td><td>'+r.od+'</td><td>'+r.cv+'%</td><td style="font-weight:600">'+fm(r.rv)+'</td><td class="bar-cell"><span>'+rp+'%</span><div class="bar-bg"><div class="bar-fill" style="width:'+rp+'%;background:#059669;"></div></div></td><td>'+r.bo.toFixed(1)+'%</td>';
            tb.appendChild(tr2);
        });
        var tc=rows.reduce(function(s,r){return s+r.ca},0),to=rows.reduce(function(s,r){return s+r.od},0);
        var tu=rows.reduce(function(s,r){return s+r.us},0),tn=rows.reduce(function(s,r){return s+r.productCount},0);
        var tt=document.createElement('tr');tt.className='totals-row';
        tt.innerHTML='<td></td><td class="cat-name-col">合计</td><td>'+tn.toLocaleString()+'</td><td>'+tv.toLocaleString()+'</td><td>100%</td><td></td><td>'+tu.toLocaleString()+'</td><td>'+(tv/tn).toFixed(1)+'</td><td></td><td>'+tc+'</td><td>'+(tv>0?(tc/tv*100).toFixed(2):'0')+'%</td><td>'+to+'</td><td>'+(tv>0?(to/tv*100).toFixed(3):'0')+'%</td><td style="font-weight:700">'+fm(tr)+'</td><td>100%</td><td></td>';
        tb.appendChild(tt);
        document.querySelectorAll('canvas.cat-sparkline').forEach(function(c){spark(c,JSON.parse(c.getAttribute('data-v')),c.getAttribute('data-c'));});
    }

    document.getElementById('catGranularitySelector').addEventListener('change',function(){
        granularity = this.value;
        populateSelector();
        render();
    });
    document.getElementById('catWeekSelector').addEventListener('change',function(){csw=this.value==='all'?-1:parseInt(this.value);render();});
    document.getElementById('catSortSelector').addEventListener('change',render);
    populateSelector();
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
    orders_file = find_orders_file()
    cat_revenue = step3b_category_revenue(orders_file) if orders_file else None
    if cat_revenue:
        print(f"📊 分类收入汇总完成（按首字母直接统计）")
    top50_output, cat_data = step4_save_json(
        products, all_sorted, cat_products, needed, active_cats, prefixBench,
        cat_revenue=cat_revenue,
    )
    step5_rebuild_dashboard(top50_output, cat_data)

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
