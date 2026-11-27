import hashlib
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_cloud_dashboard import (last_complete_week, package_site, PAGES, JSON_FILES,
                                   validate_output, validate_sources, prevent_history_loss)
from drive_snapshot import Drive, allowed


class CloudSafetyTests(unittest.TestCase):
    def test_separate_folder_access_does_not_list_parent(self):
        drive = Drive()
        folders = {'config': 'config-id', 'orders': 'orders-id', 'landing-page-data': 'pages-id'}
        with patch.object(drive, 'inventory', return_value={}) as inventory:
            drive.snapshot(folders)
            self.assertEqual(inventory.call_args_list, [
                unittest.mock.call('config-id', 'config/'),
                unittest.mock.call('pages-id', 'landing-page-data/'),
                unittest.mock.call('orders-id', 'orders/'),
            ])

    def test_invalid_folder_mapping_is_rejected_before_requests(self):
        for folders in [{}, [], {'orders':'one'},
                        {'config':'one','orders':'one','landing-page-data':'one'},
                        {'config':'one','orders':'two','landing-page-data':'../three'}]:
            with self.assertRaises(ValueError):
                Drive().snapshot(folders)

    def test_schedule_week_boundary(self):
        self.assertEqual(last_complete_week(date(2026, 11, 24)), date(2026, 11, 16))
        self.assertEqual(last_complete_week(date(2026, 11, 23)), date(2026, 11, 16))
        self.assertEqual(last_complete_week(date(2026, 11, 22)), date(2026, 11, 9))

    def test_only_source_csv_is_downloaded(self):
        for path in ['config/target-2026.csv', 'orders/订单明细表导出2026-11-22.csv',
                     'landing-page-data/full-doll/w47_2026-11-16/页面点击数.csv',
                     'landing-page-data/celebrity-sex-dolls/w12_2026-03-16 (1)/页面点击数.csv']:
            self.assertTrue(allowed(path), path)
        for path in ['.git/config', 'config/credentials.json', 'landing-page-data/update_pdp.py',
                     'landing-page-data/full-doll/w47_2026-11-16/../../hack.csv',
                     'email-migration/orders.csv', 'landing-page-data/.secrets/data.csv']:
            self.assertFalse(allowed(path), path)

    def test_missing_inputs_list_exact_files(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as result:
                validate_sources(Path(directory), date(2026, 11, 16), {'required_categories':['full-doll']})
            self.assertIn('full-doll/w47_2026-11-16/页面点击数.csv', str(result.exception))
            self.assertIn('页面浏览数2026-11-16.csv', str(result.exception))
            self.assertIn('orders/', str(result.exception))

    def test_missing_history_and_page_fail_closed(self):
        with self.assertRaises(ValueError) as result:
            validate_output({'stats':{'weeks':['w47_2026-11-16']}, 'data':{}},
                            'w47_2026-11-16', {'required_categories':['full-doll'],
                                             'baseline_weeks':['w46_2026-11-09']})
        self.assertIn('缺少历史周', str(result.exception))
        self.assertIn('full-doll', str(result.exception))

    def test_one_page_cannot_lose_history_while_other_pages_keep_it(self):
        with self.assertRaisesRegex(ValueError, 'full-doll 丢失历史周'):
            prevent_history_loss({'data': {'full-doll': {'w47': {}}, 'other': {'w46': {}, 'w47': {}}}},
                                 {'full-doll': ['w46', 'w47']})

    def test_package_never_contains_raw_orders_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / 'work/landing-page-data'
            base.mkdir(parents=True)
            for name in (*PAGES, *JSON_FILES):
                (base / name).write_text('<body></body>' if name.endswith('.html') else '{}')
            (base / 'customer.csv').write_text('private')
            (root / 'work/credentials.json').write_text('private')
            output = root / 'site'
            package_site(root / 'work', output, {'data_through':'2026-11-22', 'built_at':'2026-11-24'})
            names = {p.name for p in output.rglob('*') if p.is_file()}
            self.assertEqual(names, set(PAGES + JSON_FILES) | {'index.html','.nojekyll','update-status.json'})
            with self.assertRaises(ValueError):
                package_site(root / 'work', output, {})

    def test_changed_snapshot_is_not_accepted(self):
        content = b'csv'
        item = {'id':'test', 'size':'3', 'md5Checksum':hashlib.md5(content).hexdigest(),
                'modifiedTime':'2026-01-01T00:00:00Z'}
        drive = Drive()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(drive, 'inventory', side_effect=[{'config/target-2026.csv':item}, {}]), \
                 patch.object(drive, 'get') as get:
                get.return_value.content = content
                with self.assertRaisesRegex(RuntimeError, '发生变化'):
                    drive.download('folder', Path(directory) / 'snapshot')

    def test_checksum_mismatch_stops_download(self):
        item = {'id':'test', 'size':'3', 'md5Checksum':'invalid', 'modifiedTime':'2026-01-01T00:00:00Z'}
        drive = Drive()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(drive, 'inventory', return_value={'config/target-2026.csv':item}), \
                 patch.object(drive, 'get') as get:
                get.return_value.content = b'csv'
                with self.assertRaisesRegex(RuntimeError, '不完整'):
                    drive.download('folder', Path(directory) / 'snapshot')


if __name__ == '__main__':
    unittest.main()
