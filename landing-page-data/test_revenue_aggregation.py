#!/usr/bin/env python3
"""Regression checks for category-page revenue aggregation.

Run with: python3 test_revenue_aggregation.py
"""

from aggregate_detail import calculate_revenue_by_category, deduplicate_order_rows


def row(order, day, title, tag, qty, net, source):
    return {
        '订单名称': order,
        '小时': day,
        '产品标题': title,
        '订单标记': tag,
        '订购数量': str(qty),
        '毛销售额': str(net),
        '净销售额': str(net),
        '总销售额': str(net),
        '_source_file': source,
    }


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f'✓ {name}')


def main():
    duplicate = row(
        '#1001', '2026-07-14 09:00:00', 'B45 Breast Toy',
        '/collections/boob-job-sex-toys', 1, 699, '2026-08-09.csv'
    )
    later_snapshot = dict(duplicate, _source_file='2026-08-16.csv')
    other_line_same_order = row(
        '#1001', '2026-07-14 09:00:00', 'T71 Torso',
        '/collections/boob-job-sex-toys', 1, 399, '2026-08-16.csv'
    )
    cross_quarter = row(
        '#1002', '2026-04-01 10:00:00', 'B71 Breast Toy',
        '/collections/boob-job-sex-toys', 2, 724, '2026-08-16.csv'
    )
    shipping = row(
        '#1003', '2026-07-15 10:00:00', 'Shipping Protection',
        '/collections/boob-job-sex-toys', 1, 20, '2026-08-16.csv'
    )

    orders = deduplicate_order_rows([
        duplicate, later_snapshot, other_line_same_order, cross_quarter, shipping,
    ])
    q1_q2_q3_q4 = calculate_revenue_by_category(orders, 'boob-job-sex-toys')

    q3 = q1_q2_q3_q4['Q3']
    q2 = q1_q2_q3_q4['Q2']
    check('overlapping snapshots are deduplicated', q3['totalSales'] == 1098)
    check('multiple lines in one order keep one order count', q3['orders'] == 1)
    check('shipping protection is excluded', q3['totalSales'] != 1118)
    check('quarter boundary uses order date', q2['totalSales'] == 724)
    check('quantity is preserved for product table', q2['products'][0]['quantity'] == 2)
    check('weekly revenue uses the date-derived Monday', q3['weeklySales']['w29_2026-07-13'] == 1098)


if __name__ == '__main__':
    main()
