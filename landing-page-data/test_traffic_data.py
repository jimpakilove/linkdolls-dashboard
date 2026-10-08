"""Traffic import regressions. Run: python3 -B -m unittest test_traffic_data.py"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import aggregate_detail as a


class TrafficDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = patch.object(a, 'BASE_PATH', self.root)
        self.base.start()
        (self.root / 'pageviews').mkdir()

    def tearDown(self):
        self.base.stop()
        self.temp.cleanup()

    def landing(self, content):
        (self.root / 'pageviews' / '按登陆页面2026-09-21.csv').write_text(content, encoding='utf-8')
        return a.parse_landing_page_stats('w39_2026-09-21', 'linkdolls.com')

    def test_homepage_and_real_zero(self):
        r = self.landing('登陆页面路径,访问,在线商店访客,跳出率\n/,973,906,0\n')
        self.assertEqual(r['sessions'], 973)
        self.assertEqual(r['bounceRate'], 0)
        self.assertIsNone(r['avgSessionDuration'])
        self.assertIn('avgSessionDuration', r['missingFields'])

    def test_missing_file_and_unmatched_path(self):
        self.assertFalse(a.parse_landing_page_stats('w39_2026-09-21', 'linkdolls.com')['available'])
        r = self.landing('登陆页面路径,访问\n/collections/full-doll,100\n')
        self.assertFalse(r['available'])
        self.assertIn('未匹配', r['reason'])

    def test_invalid_value_is_not_zero(self):
        r = self.landing('登陆页面路径,访问,在线商店访客\n/,broken,906\n')
        self.assertIsNone(r['sessions'])
        self.assertEqual(r['visitors'], 906)

    def test_english_bom(self):
        r = self.landing('\ufeffLanding page path,Sessions,Online store visitors\n/,973,906\n')
        self.assertEqual(r['sessions'], 973)

    def test_exact_gsc_and_device_scope(self):
        path = self.root / '网页.csv'
        path.write_text('排名靠前的网页,点击次数,展示,点击率,排名\nhttps://linkdolls.com/collections/full-doll,1086,13208,8.22%,12.66\nhttps://linkdolls.com/,574,5475,10.48%,11.56\n', encoding='utf-8')
        self.assertEqual(a.parse_webpage(path, 'linkdolls.com')['clicks'], 574)
        self.assertFalse(a.parse_webpage(path, 'missing')['available'])
        self.assertFalse(a.gsc_scope_status(self.root, 'linkdolls.com')['available'])

    def test_devices_and_path_aliases(self):
        path = self.root / '设备.csv'
        path.write_text('设备,点击次数,展示,点击率,排名\n移动设备,10,100,10%,3\n桌面,5,100,5%,4\n', encoding='utf-8')
        self.assertEqual([d['device'] for d in a.parse_devices(path)], ['mobile', 'desktop'])
        self.assertTrue(a.is_target_url('https://linkdolls.com/collections/in-stock-usa-1', 'in-stock-usa'))
        self.assertFalse(a.is_target_url('https://linkdolls.com/collections/full-doll?sort=x', 'full-doll'))
        self.assertFalse(a.is_target_url('https://other.com/', 'linkdolls.com'))

    def test_valid_device_scope(self):
        (self.root / '网页.csv').write_text('排名靠前的网页,点击次数\nhttps://linkdolls.com/collections/full-doll,10\n', encoding='utf-8')
        self.assertTrue(a.gsc_scope_status(self.root, 'full-doll')['available'])

    def test_w40_new_import_replaces_missing_pageviews(self):
        week = 'w40_2026-09-28'
        config = {'linkdolls.com': {}, 'full-doll': {}}
        self.assertEqual(a.parse_pageviews_global(week, config), {})
        (self.root / 'pageviews' / '页面浏览数2026-09-28.csv').write_text(
            '# 20260928-20261004\n网页路径和屏幕类,浏览次数,活跃用户\n'
            '/,1457,1216\n/collections/full-doll,2576,1665\n', encoding='utf-8')
        result = a.parse_pageviews_global(week, config)
        self.assertEqual(result['linkdolls.com'], {
            'pageviews': 1457, 'activeUsers': 1216, 'available': True})
        self.assertEqual(result['full-doll']['pageviews'], 2576)

    def cart(self, content):
        (self.root / '电子商务购买_商品名称.csv').write_bytes(content)
        return a.parse_cart_adds(self.root)

    def test_cart_valid_bom_and_zero(self):
        result = self.cart('\ufeff# 导出注释\n商品名称,加入购物车的商品数\nH001,0\nH002,3\n'.encode('utf-8'))
        self.assertTrue(result['available'])
        self.assertEqual(result['items'], [{'name': 'H002', 'cartAdds': 3}])
        result = self.cart('商品名称,加入购物车的商品数\nH001,0\n'.encode('utf-8'))
        self.assertTrue(result['available'])
        self.assertEqual(result['items'], [])

    def test_cart_corrupt_encoding_is_unavailable(self):
        result = self.cart('商品名称,加入购物车的商品数\nH001,3\n'.encode('utf-8') + b'\xe3\x80?,1\n')
        self.assertFalse(result['available'])
        self.assertEqual(result['items'], [])
        self.assertIn('编码损坏', result['reason'])
        self.assertTrue(result['source'].endswith('电子商务购买_商品名称.csv'))

    def test_cart_bad_header_or_row_never_returns_partial_total(self):
        for content in ['商品名称,错误列\nH001,3\n',
                        '商品名称,加入购物车的商品数\nH001,3\nH002,broken\n',
                        '商品名称,加入购物车的商品数\nH001,3\nH002,\n',
                        '商品名称,加入购物车的商品数\nH001,3\nH002,1,extra\n',
                        '商品名称,加入购物车的商品数\nH001,3\n"H002,1\n']:
            with self.subTest(content=content):
                result = self.cart(content.encode('utf-8'))
                self.assertFalse(result['available'])
                self.assertEqual(result['items'], [])

    def test_cart_missing_and_duplicate_files(self):
        self.assertFalse(a.parse_cart_adds(self.root)['available'])
        self.cart('商品名称,加入购物车的商品数\nH001,3\n'.encode('utf-8'))
        (self.root / '电子商务购买_商品名称副本.csv').write_text('商品名称,加入购物车的商品数\n', encoding='utf-8')
        self.assertIn('多份', a.parse_cart_adds(self.root)['reason'])


if __name__ == '__main__':
    unittest.main()
