"""Validate a source snapshot, build in isolation, and package an allowlisted site."""
import argparse
import csv
from datetime import date, datetime, timedelta
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
PAGES = ('dashboard.html', 'dashboard_collection.html', 'dashboard_click_rate.html', 'dashboard_top50.html')
JSON_FILES = ('dashboard_detail.json', 'top50_data.json', 'category_data.json', 'category_revenue.json')
ASSETS = ('cloud-update.js',)
CODE = ('aggregate_detail.py', 'update_pdp.py', 'test_product_names.py', 'test_traffic_data.py',
        'test_category_revenue.py', 'test_revenue_aggregation.py', 'test_traffic_render.cjs')


def last_complete_week(today=None):
    today = today or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    return today - timedelta(days=today.weekday() + 7)


def csv_table(path):
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    lines = [line for line in lines if line.strip() and not line.startswith('#')]
    if not lines:
        raise ValueError('空表')
    reader = csv.DictReader(lines)
    return set(reader.fieldnames or []), list(reader)


def validate_sources(source, monday, policy):
    errors = []
    sunday = monday + timedelta(days=6)
    week = f'w{monday.isocalendar().week:02d}_{monday}'
    if monday.weekday() != 0 or monday > last_complete_week():
        errors.append('观察周必须是已经结束的自然周，日期为周一')
    if monday.year != 2026:
        errors.append('现有目标表及 PDP 导入器只支持 2026 年；跨年需先迁移，禁止错标年份')
    def require(relative, groups, period=False):
        path = source / relative
        if not path.is_file():
            errors.append(f'缺少文件：{relative}')
            return []
        try:
            fields, rows = csv_table(path)
            missing = [' / '.join(group) for group in groups if not fields.intersection(group)]
            if missing:
                errors.append(f'{relative} 缺少字段：' + '；'.join(missing))
            if period:
                text = path.read_text(encoding='utf-8-sig')
                dates = re.findall(r'(?<!\d)(20\d{6})(?!\d)', '\n'.join(
                    line for line in text.splitlines() if line.startswith('#')))
                if dates and (monday.strftime('%Y%m%d') not in dates or sunday.strftime('%Y%m%d') not in dates):
                    errors.append(f'{relative} 表内导出日期与文件名周次不一致')
            return rows
        except (UnicodeError, ValueError, csv.Error):
            errors.append(f'{relative} 编码或表格格式异常')
            return []
    config = require('config/target-2026.csv', [('着陆页',), ('负责人',)])
    configured = {row.get('着陆页', '').rstrip('/').split('/')[-1] for row in config}
    base = 'landing-page-data/'
    require(base + f'pageviews/页面浏览数{monday}.csv',
            [('网页路径和屏幕类',), ('浏览次数',), ('活跃用户',)], True)
    require(base + f'pageviews/电子商务购买_商品名称{monday:%m%d}.csv',
            [('商品名称',), ('查看过的商品数',), ('加入购物车的商品数',), ('结账的商品数',)], True)
    landing = sorted((source / base / 'pageviews').glob(f'按登陆*{monday}.csv'))
    if len(landing) != 1:
        errors.append(f'pageviews/按登陆*{monday}.csv 应有且仅有一份，实际 {len(landing)} 份')
    else:
        require(str(landing[0].relative_to(source)), [
            ('登陆页面路径', 'Landing page path'), ('访问', 'Sessions'),
            ('在线商店访客', 'Online store visitors'), ('跳出率', 'Bounce rate'),
            ('每次访问的页面浏览量', 'Pageviews per session'),
            ('平均访问持续时间', 'Average session duration'),
            ('有商品添加到购物车的访问', 'Sessions with cart additions'),
            ('到达结账页面的访问', 'Sessions that reached checkout'),
            ('完成结账的访问', 'Sessions that completed checkout')])
    for category in policy['required_categories']:
        if category not in configured:
            errors.append(f'目标配置缺少页面：{category}')
        folder = f'{base}{category}/{week}/'
        require(folder + '网页.csv', [('排名靠前的网页',), ('点击次数',), ('展示',), ('排名',)])
        require(folder + '查询数.csv', [('热门查询',), ('点击次数',), ('排名',)])
        require(folder + '页面点击数.csv', [('Click_URL',), ('事件数', '事件计数')], True)
        for pattern in ('购买历程_设备类别*.csv', '电子商务购买_商品名称*.csv'):
            matches = list((source / folder).glob(pattern))
            if len(matches) != 1:
                errors.append(f'{folder}{pattern} 应有且仅有一份，实际 {len(matches)} 份')
            else:
                require(str(matches[0].relative_to(source)),
                        [('设备类别',)] if pattern.startswith('购买') else [('商品名称',), ('加入购物车的商品数',)], True)
    orders = list((source / 'orders').glob('订单明细表*.csv'))
    if not orders:
        errors.append('orders/ 缺少订单明细表*.csv')
    else:
        newest = max(orders, key=lambda p: p.stat().st_mtime)
        rows = require(str(newest.relative_to(source)), [
            ('订单名称', 'Order name'), ('小时', '天', 'Day'), ('产品标题', 'Product title'),
            ('净销售额', 'Net sales'), ('订单标记', 'Order tag')])
        dates = re.findall(r'20\d{2}-\d{2}-\d{2}', newest.name)
        if not dates or date.fromisoformat(dates[-1]) < sunday:
            errors.append(f'{newest.name} 导出截止日期早于 {sunday}，不能覆盖本周')
        if not rows:
            errors.append(f'{newest.name} 没有订单行')
    if errors:
        raise ValueError('\n'.join(errors))
    return week


def run_checked(command, cwd):
    # ETL output may contain raw source details; keep it out of public Actions logs/artifacts.
    with tempfile.TemporaryFile(mode='w+') as log:
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if result.returncode:
            raise ValueError(f'生成或回归检查失败：{Path(command[0]).name} {" ".join(command[1:])}；未发布')
    print('通过：' + ' '.join([Path(command[0]).name] + command[1:]))


def validate_output(data, target, policy):
    errors = []
    weeks = set(data['stats']['weeks'])
    if target not in weeks:
        errors.append('生成结果缺少目标周')
    missing_history = set(policy['baseline_weeks']) - weeks
    if missing_history:
        errors.append('缺少历史周：' + ', '.join(sorted(missing_history)))
    for category in policy['required_categories']:
        record = data['data'].get(category, {}).get(target, {})
        if not record:
            errors.append(f'{category} 缺少 {target}')
            continue
        if not record.get('ga4', {}).get('available'):
            errors.append(f'{category} 页面浏览表没有匹配到路径')
        landing = record.get('landingPage', {})
        if not landing.get('available') or landing.get('missingFields'):
            errors.append(f'{category} 着陆页访问表未匹配或字段缺失')
        if not record.get('clickDataAvailable'):
            errors.append(f'{category} 点击数据未导入')
        if not record.get('cartStatus', {}).get('available'):
            errors.append(f'{category} 加购表未能解析')
    if errors:
        raise ValueError('\n'.join(errors))


def prevent_history_loss(data, previous):
    missing = []
    for category, weeks in previous.items():
        lost = set(weeks) - set(data['data'].get(category, {}))
        if lost:
            missing.append(f'{category} 丢失历史周：' + ', '.join(sorted(lost)))
    if missing:
        raise ValueError('\n'.join(missing))


def package_site(work, destination, metadata):
    if destination.exists():
        raise ValueError('发布目录必须不存在，防止残留文件被发布')
    public = destination / 'landing-page-data'
    public.mkdir(parents=True)
    for name in (*PAGES, *JSON_FILES, *ASSETS):
        shutil.copyfile(work / 'landing-page-data' / name, public / name)
    (destination / '.nojekyll').touch()
    (destination / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" '
        'content="0;url=landing-page-data/dashboard.html"><a href="landing-page-data/dashboard.html">打开看板</a>', encoding='utf-8')
    (public / 'update-status.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    # Add publication status only to the isolated artifact, leaving local templates intact.
    label = html.escape(f"数据截至 {metadata['data_through']} · 云端生成 {metadata['built_at']}（北京时间）")
    banner = ('<div id="cloud-update-status" style="position:fixed;bottom:0;right:0;z-index:9999;background:#eef4ff;'
              'color:#334155;font:12px/1.5 sans-serif;padding:5px 12px;border-radius:6px 0 0 0">'
              + label + '</div>')
    # A visitor can detect a stalled schedule even when no workflow runs to report it.
    deadline = datetime.fromisoformat(metadata['data_through'] + 'T12:00:00+08:00') + timedelta(days=9)
    banner += ('<script>if(Date.now()>' + str(int(deadline.timestamp() * 1000)) + '){'
               'const s=document.getElementById("cloud-update-status");'
               's.textContent="更新已逾期，请检查云端运行记录 · "+s.textContent;'
               's.style.background="#fff1d6";}</script>')
    for name in PAGES:
        path = public / name
        path.write_text(path.read_text(encoding='utf-8').replace('</body>', banner + '</body>'), encoding='utf-8')


def build(source, destination, monday, policy):
    from drive_snapshot import allowed
    target = validate_sources(source, monday, policy)
    files = sorted(p for p in source.rglob('*.csv') if allowed(p.relative_to(source).as_posix()))
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='dashboard-build-') as directory:
        work = Path(directory)
        for path in files:
            relative = path.relative_to(source)
            if path.is_symlink():
                raise ValueError(f'不支持数据文件符号链接：{relative}')
            digest.update(relative.as_posix().encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
            output = work / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
        base = work / 'landing-page-data'
        base.mkdir(exist_ok=True)
        # Preserve configured pages with no data; empty Drive folders have no CSV to copy.
        _, configured = csv_table(work / 'config/target-2026.csv')
        for row in configured:
            slug = row.get('着陆页', '').rstrip('/').split('/')[-1]
            if re.fullmatch(r'[a-z0-9][a-z0-9.-]*', slug) and slug not in ('.', '..'):
                (base / slug).mkdir(exist_ok=True)
        for name in (*CODE, *PAGES, *ASSETS):
            shutil.copyfile(REPO / 'landing-page-data' / name, base / name)
        for args in [
            ['-B', '-m', 'unittest', 'test_product_names.py', 'test_traffic_data.py'],
            ['-B', 'test_category_revenue.py'], ['-B', 'test_revenue_aggregation.py'],
            ['-B', 'update_pdp.py'], ['-B', 'aggregate_detail.py'],
        ]:
            run_checked([sys.executable, *args], base)
        data = json.loads((base / 'dashboard_detail.json').read_text())
        validate_output(data, target, policy)
        # Protect per-page history both at migration and after subsequent cloud updates.
        baseline = json.loads((REPO / 'landing-page-data/dashboard_detail.json').read_text())
        prevent_history_loss(data, baseline['data'])
        receipt = REPO / '.github/data-update-status.json'
        if receipt.exists():
            prevent_history_loss(data, json.loads(receipt.read_text())['coverage'])
        for name in JSON_FILES:
            def invalid_number(value):
                raise ValueError(f'{name} 存在非法数值 {value}')
            json.loads((base / name).read_text(), parse_constant=invalid_number)
        run_checked(['node', 'test_traffic_render.cjs'], base)
        pdp = json.loads((base / 'top50_data.json').read_text())
        if monday.isoformat() not in pdp['weekStarts'] or not pdp['products']:
            raise ValueError('PDP 生成结果缺少目标周或产品')
        # Reject unexpectedly later collection/PDP weeks rather than publish partial future data.
        if max(w.split('_')[1] for w in data['stats']['weeks']) != monday.isoformat() or max(pdp['weekStarts']) != monday.isoformat():
            raise ValueError('检测到目标周之后的数据，请核对周次和未完成上传')
        metadata = dict(data_through=str(monday + timedelta(days=6)), week=target,
                        built_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                        source_sha256=digest.hexdigest(), source_files=len(files),
                        commit=os.environ.get('GITHUB_SHA', ''),
                        coverage={category: sorted(weeks) for category, weeks in data['data'].items()},
                        required_categories=len(policy['required_categories']))
        package_site(work, destination, metadata)
    print(f'发布包已通过检查：{target}，{len(files)} 个输入文件；原始 CSV 不在发布包内')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--week-start', type=date.fromisoformat, default=last_complete_week())
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    policy = json.loads((REPO / 'config/cloud-publish-policy.json').read_text())
    try:
        if args.check_only:
            print(validate_sources(args.source, args.week_start, policy))
        else:
            build(args.source, args.output, args.week_start, policy)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + '\n')
