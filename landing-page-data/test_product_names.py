"""Product display-name regressions; no source exports are modified."""
import contextlib
import io
import unittest
from unittest.mock import patch

import update_pdp as pdp


class ProductNameTests(unittest.TestCase):
    def select(self, names):
        return pdp.select_product_name(names, 'a354')

    def test_latest_name_wins_even_if_shorter(self):
        self.assertEqual(self.select([
            ('2026-03-16', 'A354 very long obsolete product description', 100),
            ('2026-10-19', 'A354 current', 3),
        ]), 'A354 current')

    def test_latest_zero_views_still_has_a_valid_name(self):
        self.assertEqual(self.select([
            ('2026-03-16', 'A354 older', 100),
            ('2026-10-19', 'A354 latest', 0),
        ]), 'A354 latest')

    def test_dates_not_input_order_determine_latest(self):
        self.assertEqual(self.select([
            ('2026-10-19', 'A354 latest', 1),
            ('2026-03-16', 'A354 earlier and longer', 50),
        ]), 'A354 latest')

    def test_blank_name_does_not_replace_last_valid_name(self):
        self.assertEqual(self.select([
            ('2026-10-12', ' A354 valid ', 1),
            ('2026-10-19', '   ', 10),
        ]), 'A354 valid')
        self.assertEqual(self.select([]), 'a354')

    def test_same_week_selects_name_with_most_combined_views(self):
        self.assertEqual(self.select([
            ('2026-10-19', 'A354 minority very long name', 5),
            ('2026-10-19', 'A354 majority', 3),
            ('2026-10-19', 'A354 majority', 4),
        ]), 'A354 majority')

    def test_same_week_tie_is_independent_of_row_order(self):
        names = [('2026-10-19', 'A354 B', 2), ('2026-10-19', 'A354 A', 2)]
        self.assertEqual(self.select(names), self.select(list(reversed(names))))

    def test_import_changes_label_without_splitting_code_or_metrics(self):
        weeks = [('W12', '0316', '2026-03-16'), ('W43', '1019', '2026-10-19')]
        fields = ['查看过的商品数', '活跃用户', '加入购物车的商品数',
                  '结账的商品数', '已购买的商品数', '商品收入', '跳出率']
        def row(name, views):
            return {'商品名称': name, **dict(zip(fields, [str(views), '2', '1', '1', '1', '10', '0.1']))}
        exports = [[row('A354 long historical title', 3)], [row('A354 current', 53)]]
        with patch.object(pdp, 'WEEKS', weeks), \
                patch.object(pdp.os.path, 'exists', return_value=True), \
                patch.object(pdp, 'read_ecom_csv', side_effect=exports), \
                contextlib.redirect_stdout(io.StringIO()):
            products = pdp.step1_read_ecommerce()
        self.assertEqual(list(products), ['a354'])
        product = products['a354']
        self.assertEqual(product['name'], 'A354 current')
        self.assertEqual(product['weeklyViews'], [3, 53])
        self.assertEqual(product['weeklyUsers'], [2, 2])
        for key in ['weeklyCarts', 'weeklyCheckouts', 'weeklyPurchased']:
            self.assertEqual(product[key], [1, 1])
        self.assertEqual(product['weeklyRevenue'], [10.0, 10.0])
        self.assertEqual(product['weeklyBounce'], [10.0, 10.0])
        self.assertNotIn('names', product)


if __name__ == '__main__':
    unittest.main()
