#!/usr/bin/env python3
"""
Tests for step3b_category_revenue() and step3_match_orders() code-matching logic.
Run with: python3 test_category_revenue.py
"""

import sys
import os
import csv
import io
import tempfile

# ── minimal stubs so we can import the function under test ──────────────────
# We'll test the function in isolation by patching its dependencies.

SKIP_ORDER_KW = ['shipping protection', 'route', 'extended warranty', 'custom']

CAT_NAMES = {
    'f': 'Full Doll', 'a': 'Ass', 't': 'Torso', 'h': 'Head',
    'p': 'Pussy', 'v': 'Vajankle', 'l': 'Legs', 'b': 'Boob',
    'm': 'Male', 'd': 'Dildo', 'other': 'Other'
}

# Week boundaries used in tests
WEEK_STARTS = ['2026-01-05', '2026-01-12', '2026-01-19', '2026-01-26',
               '2026-02-02', '2026-02-09']
WEEK_END = '2026-02-16'
WEEK_NAMES = ['W2', 'W3', 'W4', 'W5', 'W6', 'W7']

def date_to_week(d):
    if d < WEEK_STARTS[0] or d >= WEEK_END:
        return -1
    for i in range(len(WEEK_STARTS) - 1, -1, -1):
        if d >= WEEK_STARTS[i]:
            return i
    return -1

# ── function under test (to be imported once implemented) ───────────────────
# We import it here; before implementation this will raise ImportError → RED
try:
    from update_pdp import step3b_category_revenue as _step3b
    from update_pdp import step3_match_orders as _step3_match_orders
    # Wrap to inject our test stubs instead of module globals
    def step3b_category_revenue(orders_file):
        return _step3b(
            orders_file,
            week_starts=WEEK_STARTS,
            week_end=WEEK_END,
            n_weeks=len(WEEK_NAMES),
            skip_kw=SKIP_ORDER_KW,
            cat_names=CAT_NAMES,
        )
    IMPORTED = True
except Exception as e:
    IMPORTED = False
    IMPORT_ERROR = str(e)

# ── helpers ─────────────────────────────────────────────────────────────────

def make_csv(rows):
    """Write list-of-dicts to a temp CSV file, return path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                    delete=False, encoding='utf-8-sig')
    headers = ['订单名称', '天', '产品标题', '订单标记', '订购数量',
               '毛销售额', '净销售额', '总销售额']
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    f.close()
    return f.name

def row(order='#1001', day='2026-01-05', title='A599 Big Booty Torso',
        tag='', qty=1, gross=100, net=100, total=100):
    return {'订单名称': order, '天': day, '产品标题': title,
            '订单标记': tag, '订购数量': qty,
            '毛销售额': gross, '净销售额': net, '总销售额': total}

# ── tests ────────────────────────────────────────────────────────────────────

passed = failed = 0

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f'  ✓ {name}')
        passed += 1
    else:
        print(f'  ✗ {name}{": " + detail if detail else ""}')
        failed += 1

def test_import():
    """Function must be importable with correct signature."""
    check('step3b_category_revenue importable', IMPORTED,
          IMPORT_ERROR if not IMPORTED else '')

def test_single_order_correct_week_and_category():
    """A product starting with 'A' in W2 adds its net sales to cat 'a', week 0."""
    path = make_csv([row(day='2026-01-05', title='A599 Big Booty', net=299)])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('a category exists in result', 'a' in result)
    check('week 0 revenue = 299', result.get('a', {}).get('weeklyRevenue', [None]*6)[0] == 299.0)
    check('week 0 orders = 1',   result.get('a', {}).get('weeklyOrders',  [None]*6)[0] == 1)

def test_shipping_protection_skipped():
    """Rows containing 'Shipping Protection' must be ignored."""
    path = make_csv([row(title='Shipping Protection', net=10)])
    result = step3b_category_revenue(path)
    os.unlink(path)
    total = sum(result.get(c, {}).get('totalRevenue', 0) for c in CAT_NAMES)
    check('shipping protection not counted', total == 0)

def test_out_of_range_date_skipped():
    """Orders outside the week window return -1 from date_to_week → skipped."""
    path = make_csv([row(day='2025-12-01', title='T521 Torso', net=199)])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('out-of-range order not counted',
          result.get('t', {}).get('totalRevenue', 0) == 0)

def test_multiple_categories_and_weeks():
    """Two orders in different categories and weeks land in the right buckets."""
    path = make_csv([
        row(order='#1', day='2026-01-05', title='F8045 Full Doll', net=2000),  # W2 → wi=0
        row(order='#2', day='2026-01-12', title='T521 Torso', net=199),        # W3 → wi=1
    ])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('f week 0 = 2000', result.get('f', {}).get('weeklyRevenue', [])[0] == 2000.0)
    check('t week 1 = 199',  result.get('t', {}).get('weeklyRevenue', [])[1] == 199.0)
    check('f week 1 = 0',    result.get('f', {}).get('weeklyRevenue', [])[1] == 0.0)

def test_total_revenue_and_orders():
    """totalRevenue and totalOrders are sums across all weeks."""
    path = make_csv([
        row(order='#1', day='2026-01-05', title='A664 Ass Torso', net=300),
        row(order='#2', day='2026-01-12', title='A499 Bubble Butt', net=200),
    ])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('a totalRevenue = 500',
          result.get('a', {}).get('totalRevenue', 0) == 500.0)
    check('a totalOrders = 2',
          result.get('a', {}).get('totalOrders', 0) == 2)

def test_duplicate_order_rows_counted_once():
    """Identical (order, title, day, net) rows are deduplicated."""
    path = make_csv([
        row(order='#1', day='2026-01-05', title='H442 Head', net=568),
        row(order='#1', day='2026-01-05', title='H442 Head', net=568),
    ])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('duplicate order counted once',
          result.get('h', {}).get('totalRevenue', 0) == 568.0)

def test_unknown_first_char_goes_to_other():
    """Products starting with a digit or unknown letter go to 'other'."""
    path = make_csv([row(day='2026-01-05', title='599 Legacy Torso', net=150)])
    result = step3b_category_revenue(path)
    os.unlink(path)
    check('digit-prefixed product goes to other',
          result.get('other', {}).get('totalRevenue', 0) == 150.0)


# ── step3_match_orders: code-exact matching tests ────────────────────────────

def make_products_and_needed(entries):
    """
    entries: list of (product_name, code)
    Returns (products dict, needed set) compatible with step3_match_orders.
    """
    n_weeks = len(WEEK_NAMES)
    products = {}
    needed = set()
    for name, code in entries:
        letter = code[0].lower() if code else '?'
        products[name] = {
            'name': name, 'code': code,
            'category': letter, 'firstChar': letter,
            'weeklyViews': [10] * n_weeks,
            'weeklyRevenue': [0.0] * n_weeks,
            'weeklyOrderCount': [0] * n_weeks,
            'revenue': 0.0, 'orderCount': 0, 'totalRevenue': 0.0,
        }
        needed.add(name)
    return products, needed


def run_step3(products, needed, csv_rows):
    """Write csv_rows to a temp file, run step3_match_orders with test week config, return products."""
    import update_pdp as m
    orig_weeks = m.WEEKS
    orig_week_end = m.WEEK_END
    orig_week_starts = m.WEEK_STARTS
    orig_week_names = m.WEEK_NAMES
    orig_find = m.find_orders_file

    path = make_csv(csv_rows)
    m.WEEKS = list(zip(WEEK_NAMES, [''] * len(WEEK_NAMES), WEEK_STARTS))
    m.WEEK_END = WEEK_END
    m.WEEK_STARTS = WEEK_STARTS
    m.WEEK_NAMES = WEEK_NAMES
    m.find_orders_file = lambda: path

    try:
        _step3_match_orders(products, needed)
    finally:
        m.WEEKS = orig_weeks
        m.WEEK_END = orig_week_end
        m.WEEK_STARTS = orig_week_starts
        m.WEEK_NAMES = orig_week_names
        m.find_orders_file = orig_find
        os.unlink(path)

    return products


def test_code_match_exact():
    """订单 'A599 (83lb)...' 精确匹配 code='a599' 的产品。"""
    products, needed = make_products_and_needed([
        ('A599 Big Booty Sex Doll Torso', 'a599'),
    ])
    run_step3(products, needed, [
        row(day='2026-01-05', title='A599 (83lb) Sucking Doggy Style', net=299),
    ])
    p = products['A599 Big Booty Sex Doll Torso']
    check('a599 matched: week 0 revenue = 299', p['weeklyRevenue'][0] == 299.0)
    check('a599 matched: orderCount = 1', p['orderCount'] == 1)


def test_code_no_partial_match():
    """F6533 不能匹配 code='f653' 的产品（数字编号必须完整）。"""
    products, needed = make_products_and_needed([
        ('F653 Some Doll', 'f653'),
    ])
    run_step3(products, needed, [
        row(day='2026-01-05', title='F6533 Bigger Doll', net=500),
    ])
    p = products['F653 Some Doll']
    check('f6533 does NOT match f653', p['revenue'] == 0.0)


def test_code_no_reverse_partial_match():
    """F653 不能匹配 code='f6533' 的产品。"""
    products, needed = make_products_and_needed([
        ('F6533 Bigger Doll', 'f6533'),
    ])
    run_step3(products, needed, [
        row(day='2026-01-05', title='F653 Some Doll', net=500),
    ])
    p = products['F6533 Bigger Doll']
    check('f653 does NOT match f6533', p['revenue'] == 0.0)


def test_code_match_with_dash_suffix():
    """订单标题 'A664-(37.5lb)...' 仍能匹配 code='a664'（连字符在编号之后）。"""
    products, needed = make_products_and_needed([
        ('A664 Silicone Butt Torso', 'a664'),
    ])
    run_step3(products, needed, [
        row(day='2026-01-05', title='A664-(37.5lb) Silicone Big Ass', net=399),
    ])
    p = products['A664 Silicone Butt Torso']
    check('a664- title matches a664', p['weeklyRevenue'][0] == 399.0)


# ── run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('Running tests...\n')
    print('── step3b_category_revenue ──')
    test_import()
    if IMPORTED:
        test_single_order_correct_week_and_category()
        test_shipping_protection_skipped()
        test_out_of_range_date_skipped()
        test_multiple_categories_and_weeks()
        test_total_revenue_and_orders()
        test_duplicate_order_rows_counted_once()
        test_unknown_first_char_goes_to_other()

        print('\n── step3_match_orders (code-exact matching) ──')
        test_code_match_exact()
        test_code_no_partial_match()
        test_code_no_reverse_partial_match()
        test_code_match_with_dash_suffix()

    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)

    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
