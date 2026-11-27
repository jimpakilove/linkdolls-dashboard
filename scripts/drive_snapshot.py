"""Download only dashboard CSV inputs from one read-only Drive folder.

Uses Application Default Credentials (Workload Identity Federation preferred).
Never downloads executable code, follows shortcuts, or falls back to Git CSVs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import time

FOLDER = 'application/vnd.google-apps.folder'
FIELDS = 'id,name,mimeType,modifiedTime,size,md5Checksum,version'
SCOPE = 'https://www.googleapis.com/auth/drive.readonly'


def allowed(path, folder=False):
    parts = PurePosixPath(path).parts
    if not parts or any(p in ('.', '..') or p.startswith('.') or '\\' in p or
                        any(ord(c) < 32 for c in p) for p in parts):
        return False
    if folder:
        if len(parts) == 1:
            return parts[0] in ('landing-page-data', 'orders', 'config')
        if parts[0] != 'landing-page-data':
            return False
        if len(parts) == 2:
            return bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]*', parts[1]))
        # Old Drive exports include " (1)" folders consumed by the existing PDP importer.
        # Preserve those inputs during migration; do not silently change historical counts.
        return len(parts) == 3 and bool(re.fullmatch(r'w\d{2}_\d{4}-\d{2}-\d{2}(?: \(\d+\))?', parts[2]))
    if path == 'config/target-2026.csv':
        return True
    if parts[0] == 'orders' and len(parts) == 2:
        return parts[-1].endswith('.csv') and parts[-1].startswith(('订单明细表', 'orders_detail_'))
    return (parts[0] == 'landing-page-data' and parts[-1].endswith('.csv') and
            ((len(parts) == 3 and parts[1] in ('pageviews', 'clicks')) or
             (len(parts) == 4 and allowed('/'.join(parts[:-1]), folder=True))))


class Drive:
    def __init__(self):
        self.local = threading.local()

    def get(self, path, **params):
        if not hasattr(self.local, 'session'):
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=[SCOPE])
            self.local.session = AuthorizedSession(credentials)
        for attempt in range(6):
            response = self.local.session.get(
                'https://www.googleapis.com/drive/v3/' + path,
                params=params, timeout=90)
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                continue
            # Do not print response bodies, request URLs, or credential details.
            if response.status_code != 200:
                raise RuntimeError(f'Drive 请求失败 (HTTP {response.status_code})；检查只读授权和 API 配额')
            return response
        raise RuntimeError('Drive 暂时不可用，多次重试失败')

    def inventory(self, root, prefix=''):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', root):
            raise ValueError('DRIVE_FOLDER_ID 应为文件夹 ID，不是完整链接')
        records = {}
        def walk(folder_id, prefix=''):
            token = None
            names = set()
            while True:
                params = dict(q=f"'{folder_id}' in parents and trashed = false",
                              fields=f'nextPageToken,incompleteSearch,files({FIELDS})',
                              pageSize=1000, supportsAllDrives=True,
                              includeItemsFromAllDrives=True)
                if token:
                    params['pageToken'] = token
                page = self.get('files', **params).json()
                if page.get('incompleteSearch'):
                    raise RuntimeError('云盘清单不完整，停止发布')
                for item in page.get('files', []):
                    name = item['name']
                    if '/' in name or '\\' in name or name in ('.', '..'):
                        # Drive permits names that cannot be local path components.
                        # They cannot be allowlisted inputs. Ignore rather than let an
                        # unrelated file stop the export; required inputs are checked later.
                        continue
                    path = prefix + name
                    is_folder = item['mimeType'] == FOLDER
                    if not allowed(path, is_folder):
                        continue
                    if name in names:
                        raise RuntimeError(f'云盘存在重复名称：{path}')
                    names.add(name)
                    if is_folder:
                        walk(item['id'], path + '/')
                    else:
                        if not item.get('md5Checksum'):
                            raise RuntimeError(f'需上传原始 CSV 文件（不支持快捷方式或在线表格）：{path}')
                        records[path] = {k: item[k] for k in FIELDS.split(',') if k in item}
                token = page.get('nextPageToken')
                if not token:
                    return
        walk(root, prefix)
        return records

    def snapshot(self, roots):
        if isinstance(roots, str):
            return self.inventory(roots)
        if not isinstance(roots, dict) or set(roots) != {'config', 'orders', 'landing-page-data'}:
            raise ValueError('DRIVE_FOLDER_IDS 必须包含 config、orders、landing-page-data 三个目录 ID')
        if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value)
               for value in roots.values()):
            raise ValueError('云盘子目录 ID 格式不正确')
        if len(set(roots.values())) != 3:
            raise ValueError('三个云盘子目录必须分别指向不同目录')
        records = {}
        for name, folder_id in sorted(roots.items()):
            records.update(self.inventory(folder_id, name + '/'))
        return records

    def download(self, root, destination):
        destination = Path(destination)
        if destination.exists():
            raise RuntimeError('下载目录必须是新的空目录，避免混入旧数据')
        print('正在读取云盘源文件清单…', flush=True)
        before = self.snapshot(root)
        if not before:
            raise RuntimeError('指定云盘文件夹没有可用数据；应包含 config、orders、landing-page-data')
        now = datetime.now(timezone.utc)
        for path, item in before.items():
            changed = datetime.fromisoformat(item['modifiedTime'].replace('Z', '+00:00'))
            if (now - changed).total_seconds() < 300:
                raise RuntimeError(f'文件刚上传，请至少等待 5 分钟后重试：{path}')
        destination.mkdir(parents=True)
        print(f'清单包含 {len(before)} 个源文件，开始下载并校验…', flush=True)
        def download_one(pair):
            path, item = pair
            content = self.get('files/' + item['id'], alt='media', supportsAllDrives=True).content
            if len(content) != int(item['size']) or hashlib.md5(content).hexdigest() != item['md5Checksum']:
                raise RuntimeError(f'文件下载不完整或下载中发生变化：{path}')
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            stamp = datetime.fromisoformat(item['modifiedTime'].replace('Z', '+00:00')).timestamp()
            os.utime(target, (stamp, stamp))  # PDP selects the most recently modified order export.
        with ThreadPoolExecutor(max_workers=8) as pool:
            for count, _ in enumerate(pool.map(download_one, before.items()), start=1):
                if count % 1000 == 0:
                    print(f'已下载并校验 {count}/{len(before)} 个文件', flush=True)
        print('正在复核云盘清单是否发生变化…', flush=True)
        if self.snapshot(root) != before:
            raise RuntimeError('下载期间云盘内容发生变化，停止发布；请待上传结束后重试')
        # Private build evidence only; never included in the website artifact.
        (destination / 'source-manifest.json').write_text(
            json.dumps(before, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        print(f'已核验并下载 {len(before)} 个源文件')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder-id', default=os.environ.get('DRIVE_FOLDER_ID', ''))
    parser.add_argument('--folders-json', default=os.environ.get('DRIVE_FOLDER_IDS', ''))
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    try:
        roots = json.loads(args.folders_json) if args.folders_json else args.folder_id
        Drive().download(roots, args.destination)
    except (RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
