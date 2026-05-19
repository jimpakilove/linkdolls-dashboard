#!/usr/bin/env python3
"""
完整数据聚合脚本
- 读取各分类页的周数据（GSC/GA4等）
- 读取config/pages.csv（目标、负责人）
- 读取data/orders/orders_2026_Q1.csv（订单数据，按Order tag归因）
- 新增：按产品首字母+周汇总收入（输出 category_revenue.json）
"""

import os
import json
from pathlib import Path
import csv
import re
from collections import defaultdict
from datetime import datetime, timedelta

BASE_PATH = Path(__file__).parent.resolve()

def parse_csv(filepath):
    """解析CSV文件"""
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            header_line = None
            data_start = 0
            for i, line in enumerate(lines):
                if line.startswith('#') or not line.strip():
                    continue
                header_line = [h.strip() for h in line.strip().split(',')]
                data_start = i + 1
                break
            
            if header_line:
                for line in lines[data_start:]:
                    if line.strip() and not line.startswith('#'):
                        values = line.strip().split(',')
                        if len(values) >= len(header_line):
                            row = dict(zip(header_line, [v.strip() for v in values]))
                            data.append(row)
    except Exception as e:
        print(f"解析CSV失败 {filepath}: {e}")
    return data

def load_page_config():
    """读取页面配置"""
    config = {}
    config_path = Path('/Users/apple/Desktop/linkdolls dashboard/config/target-2026.csv')
    
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        return config
    
    with open(config_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 字段名是中文
            url = row.get('着陆页', '').strip()
            if not url:
                continue
            
            # 从URL提取category名称
            if url.startswith('/collections/'):
                cat = url.replace('/collections/', '')
            elif url == '/linkdolls.com':
                cat = 'linkdolls.com'
            elif url.startswith('/pages/'):
                cat = url.replace('/pages/', '')
            else:
                cat = url.strip('/')
            
            config[cat] = {
                'owner': row.get('负责人', '-').strip(),
                'q1_traffic_goal': int(float(row.get('q1流量目标', 0) or 0)),
                'q1_revenue_goal': int(float(str(row.get('q1销售金额', 0) or '0').replace('$', '').replace(',', '').replace(' ', ''))),
                'q2_traffic_goal': int(float(row.get('q2流量目标', 0) or 0)),
                'q2_revenue_goal': int(float(str(row.get('q2销售金额', 0) or '0').replace('$', '').replace(',', '').replace(' ', ''))),
                'q3_traffic_goal': int(float(row.get('q3流量目标', 0) or 0)),
                'q3_revenue_goal': int(float(str(row.get('q3销售金额', 0) or '0').replace('$', '').replace(',', '').replace(' ', ''))),
                'q4_traffic_goal': int(float(row.get('q4流量目标', 0) or 0)),
                'q4_revenue_goal': int(float(str(row.get('q4销售金额', 0) or '0').replace('$', '').replace(',', '').replace(' ', '')))
            }
    
    print(f"📋 加载配置: {len(config)} 个页面")
    return config

def load_orders_all():
    """读取订单数据 - 自动查找最新的订单文件"""
    orders_dir = Path('/Users/apple/Desktop/linkdolls dashboard/orders')
    
    if not orders_dir.exists():
        print(f"订单目录不存在: {orders_dir}")
        return []
    
    import glob
    # 三种文件命名规范
    pattern1 = str(orders_dir / 'orders_detail_*_tags.csv')
    pattern2 = str(orders_dir / '订单明细表导出*.csv')
    pattern3 = str(orders_dir / '订单明细表*.csv')
    
    files = sorted(set(glob.glob(pattern1) + glob.glob(pattern2) + glob.glob(pattern3)), reverse=True)
    
    if not files:
        print(f"没有找到订单文件")
        all_files = list(orders_dir.iterdir())
        print(f"目录中的文件: {[f.name for f in all_files]}")
        return []
    
    # 读取所有订单文件并合并
    orders = []
    for filepath in files:
        orders_path = Path(filepath)
        print(f"📦 读取订单文件: {orders_path.name}")
        # 使用 utf-8-sig 自动处理 BOM，兼容 Excel/Numbers 导出的 CSV
        with open(orders_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                orders.append(row)
    
    print(f"📦 共加载订单: {len(orders)} 行（{len(files)} 个文件）")
    return orders

# 全局缓存：row id → normalized keys 映射
_field_cache = {}

def get_field(row, field, default=''):
    """兼容中英文字段名，自动处理 BOM、空格、大小写"""
    mapping = {
        'Order name': '订单名称',
        'Product title': '产品标题',
        'Order tag': '订单标记',
        'Net sales': '净销售额',
        'Day': '天',
        'Gross sales': '毛销售额',
        'Total sales': '总销售额'
    }

    # 构建标准化的字段名查找表（去空格、去 BOM、转小写）
    row_id = id(row)
    if row_id not in _field_cache:
        _field_cache[row_id] = {k.strip().strip('\ufeff').lower(): k for k in row.keys()}
    normalized_keys = _field_cache[row_id]

    # 1. 精确匹配
    if field in row:
        return row.get(field, default)

    # 2. 标准化匹配（去空格、去 BOM、忽略大小写）
    normalized_field = field.strip().strip('\ufeff').lower()
    if normalized_field in normalized_keys:
        return row.get(normalized_keys[normalized_field], default)

    # 3. 映射后的中文名匹配
    cn_field = mapping.get(field, field)
    if cn_field in row:
        return row.get(cn_field, default)

    # 4. 兼容旧字段名（月→天）
    fallback = {'天': '月', '月': '天'}
    if cn_field in fallback and fallback[cn_field] in row:
        return row.get(fallback[cn_field], default)

    return default

def normalize_order_tag(tag):
    """去掉 Order tag 中的语言前缀，处理 Shopify 截断的特殊映射"""
    tag = tag.strip()
    # 去掉语言前缀
    normalized = re.sub(r'^/(en-ca|de|ja|fr|es|pt|it|ko|zh|en|nl|sv|da|no|fi|pl|ru|ar|th|vi|id|ms|tr|he|cs|hu|ro|uk|el|bg|hr|sk|sl|et|lv|lt)/', '/', tag)
    
    # Shopify Order tag 长度限制导致的截断映射
    # 被截断的短名称 -> 完整分类名
    TRUNCATED_MAP = {
        '/collections/sex-doll-torso-dildo': '/collections/sex-doll-torso-dildo-for-woman',
        '/collections/fake-pussy-fake-vagina': '/collections/fake-pussy-fake-vagina-sex-toys',
    }
    if normalized in TRUNCATED_MAP:
        normalized = TRUNCATED_MAP[normalized]
    
    return normalized

def calculate_revenue_by_category(orders_all, category):
    """按页面归因计算收入数据 - 按季度拆分"""
    url_path = f"/collections/{category}"
    if category == 'linkdolls.com':
        url_path = 'linkdolls.com'
    
    filtered = [o for o in orders_all if normalize_order_tag(get_field(o, 'Order tag')) == url_path]
    
    quarter_months = {
        'Q1': ['01', '02', '03'],
        'Q2': ['04', '05', '06'],
        'Q3': ['07', '08', '09'],
        'Q4': ['10', '11', '12']
    }
    
    result = {}
    for q, months in quarter_months.items():
        q_orders = []
        for o in filtered:
            day_raw = get_field(o, 'Day', '').strip()
            day = normalize_date(day_raw)
            if len(day) >= 7:
                month = day[5:7]
                if month in months:
                    q_orders.append(o)
        
        if not q_orders:
            result[q] = {
                'orders': 0,
                'totalSales': 0,
                'avgPrice': 0,
                'products': [],
                'monthlySales': {m: 0 for m in months}
            }
            continue
        
        total_sales = sum(float(get_field(o, 'Net sales', 0) or 0) for o in q_orders)
        unique_orders = set(get_field(o, 'Order name', '') for o in q_orders)
        order_count = len(unique_orders)
        avg_price = round(total_sales / order_count, 2) if order_count > 0 else 0
        
        product_sales = defaultdict(lambda: {'orders': 0, 'sales': 0})
        for o in q_orders:
            product_title = get_field(o, 'Product title', '').strip()
            if 'Shipping' in product_title:
                continue
            net_sales = float(get_field(o, 'Net sales', 0) or 0)
            product_sales[product_title]['orders'] += 1
            product_sales[product_title]['sales'] += net_sales
        
        products = sorted(
            [{'name': k, 'orders': v['orders'], 'sales': round(v['sales'], 2)} for k, v in product_sales.items()],
            key=lambda x: x['sales'],
            reverse=True
        )[:10]
        
        monthly_sales = defaultdict(float)
        for o in q_orders:
            day = get_field(o, 'Day', '').strip()
            if len(day) >= 7:
                month = day[5:7]
                monthly_sales[month] += float(get_field(o, 'Net sales', 0) or 0)
        
        result[q] = {
            'orders': order_count,
            'totalSales': round(total_sales, 2),
            'avgPrice': avg_price,
            'products': products,
            'monthlySales': {m: round(monthly_sales.get(m, 0), 2) for m in months}
        }
    
    return result

# ==================== 新增：按产品首字母+周汇总 ====================

def extract_prefix_from_title(title):
    """
    从产品标题中提取首字母分类
    "A599 (83lb) Sucking Doggy Style..." → "a"
    "F555-161cm(5ft3)/52.5kg H Cup..." → "f"
    "T908K - 94.8 lbs Cinnamon-TPE Gel..." → "t"
    """
    title = title.strip()
    # 匹配开头的字母+数字组合
    match = re.match(r'^([A-Za-z]+)\d', title)
    if match:
        return match.group(1).lower()[0]  # 取首字母小写
    return 'other'


def build_week_mapping(weeks_set):
    """
    从周文件夹名称构建 W10 → (起始日期, 结束日期) 映射
    weeks_set: {'w10_2026-03-02', 'w11_2026-03-09', ...}
    返回: {'W10': ('2026-03-02', '2026-03-08'), 'W11': ('2026-03-09', '2026-03-15'), ...}
    """
    mapping = {}
    for wf in weeks_set:
        match = re.match(r'w(\d+)_(\d{4}-\d{2}-\d{2})', wf)
        if match:
            week_num = int(match.group(1))
            start_str = match.group(2)
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
            end_date = start_date + timedelta(days=6)
            mapping[f'W{week_num}'] = (start_str, end_date.strftime('%Y-%m-%d'))
    return mapping


def normalize_date(date_str):
    """
    将日期格式统一转换为 YYYY-MM-DD
    支持: 2026/5/4, 2026/05/04, 2026-5-4, 2026-05-04
    """
    if not date_str:
        return ''
    date_str = date_str.strip()
    # 统一用 - 替换 /
    date_str = date_str.replace('/', '-')
    parts = date_str.split('-')
    if len(parts) == 3:
        try:
            year = parts[0]
            month = int(parts[1])
            day = int(parts[2])
            return f"{year}-{month:02d}-{day:02d}"
        except (ValueError, IndexError):
            return ''
    return date_str


def calculate_category_weekly_revenue(orders_all, week_mapping):
    """
    按产品首字母 + 周 汇总订单数据
    返回: {
        'a': {'W10': {'orders': 3, 'revenue': 4536.34}, 'W11': {...}, ...},
        'f': {...},
        ...
    }
    """
    result = defaultdict(lambda: defaultdict(lambda: {'orders': 0, 'revenue': 0.0}))

    for order in orders_all:
        title = get_field(order, 'Product title', '')
        if not title or 'Shipping' in title:
            continue

        prefix = extract_prefix_from_title(title)
        day_raw = get_field(order, 'Day', '').strip()
        day = normalize_date(day_raw)

        if not day:
            continue

        # 确定属于哪一周
        matched_week = None
        for week, (start_str, end_str) in week_mapping.items():
            if start_str <= day <= end_str:
                matched_week = week
                break

        if not matched_week:
            continue

        net_sales = float(get_field(order, 'Net sales', 0) or 0)
        result[prefix][matched_week]['orders'] += 1
        result[prefix][matched_week]['revenue'] += net_sales

    return result

# ==================== 其他辅助函数（保持原样）====================

def parse_clicks_global(week_folder):
    # ... 保持不变 ...
    result = []
    clicks_dir = BASE_PATH / 'clicks'
    if not clicks_dir.exists():
        return result
    match = re.match(r'w\d+_(\d{4}-\d{2}-\d{2})', week_folder)
    if not match:
        return result
    target_date = match.group(1)
    target_file = clicks_dir / f'页面元素点击数{target_date}.csv'
    if not target_file.exists():
        return result
    rank = 0
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#') or 'Click_URL' in s or '总计' in s:
                    continue
                parts = s.split(',')
                if len(parts) >= 2 and parts[0].strip().startswith('http'):
                    rank += 1
                    url = parts[0].strip()
                    events = int(parts[1] or 0)
                    is_filter = '?' in url and '/products/' not in url
                    if '/products/' in url:
                        name = "产品：" + url.split('/products/')[-1].split('?')[0][:35]
                    elif '?' in url:
                        name = "筛选：" + url.split('?')[-1][:25]
                    else:
                        name = url.split('//')[-1][:35]
                    result.append({'rank': rank, 'type': 'f' if is_filter else 'p', 'name': name, 'clicks': events, 'url': url})
    except Exception as e:
        print(f"读取页面元素点击数失败: {e}")
    return result

def parse_clicks(filepath):
    # ... 保持不变 ...
    clicks = []
    rank = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip() or 'Click_URL' in line or '总计' in line:
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 2 and parts[0].strip().startswith('http'):
                    rank += 1
                    url = parts[0].strip()
                    events = int(parts[1] or 0)
                    if '?' in url and '/products/' not in url:
                        link_type = 'f'
                        name = "筛选：" + url.split('?')[-1][:25]
                    elif '/products/' in url:
                        link_type = 'p'
                        name = "产品：" + url.split('/products/')[-1].split('?')[0][:35]
                    elif '/collections/' in url:
                        link_type = 'n'
                        name = "导航：" + url.split('/collections/')[-1].split('?')[0][:35]
                    else:
                        link_type = 'n'
                        name = url.split('//')[-1][:35]
                    clicks.append({'rank': rank, 'type': link_type, 'name': name, 'clicks': events, 'url': url})
    except:
        pass
    return clicks

def parse_conversion(filepath):
    # ... 保持不变 ...
    conversion = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 6:
                    device = parts[0].strip().lower()
                    if device in ['mobile', 'desktop', 'tablet']:
                        conversion[device] = {
                            'sessions': int(parts[1] or 0),
                            'viewProduct': int(parts[2] or 0),
                            'addToCart': int(parts[3] or 0),
                            'checkout': int(parts[4] or 0),
                            'purchase': int(parts[5] or 0)
                        }
    except:
        pass
    return conversion

def parse_devices(filepath):
    # ... 保持不变 ...
    devices = []
    for row in parse_csv(filepath):
        if row.get('设备'):
            devices.append({
                'device': row['设备'],
                'clicks': int(row.get('点击次数', 0) or 0),
                'impressions': int(row.get('展示', 0) or 0),
                'ctr': row.get('点击率', '0%'),
                'rank': float(row.get('排名', 0) or 0)
            })
    return devices

def parse_queries(filepath):
    # ... 保持不变 ...
    queries = []
    for row in parse_csv(filepath):
        if row.get('热门查询'):
            try:
                rank = float(str(row.get('排名', 999) or 999).replace('%', ''))
                clicks = int(row.get('点击次数', 0) or 0)
                ctr_str = row.get('点击率', '0%') or '0%'
                ctr = float(ctr_str.replace('%', ''))
                imp = int(row.get('展示', 0) or 0)
            except:
                continue
            if rank <= 3:
                tag = 'top3'
            elif rank <= 10:
                tag = 'top10'
            elif rank <= 20:
                tag = 'opp'
            elif clicks == 0:
                tag = 'zero'
            else:
                tag = 'ctr'
            queries.append({'kw': row['热门查询'], 'rank': round(rank, 2), 'clicks': clicks, 'imp': imp, 'ctr': round(ctr, 1), 'tag': tag})
    return queries

def parse_webpage(filepath):
    # ... 保持不变 ...
    result = {'clicks': 0, 'impressions': 0, 'ctr': 0, 'rank': 0, 'url': ''}
    for row in parse_csv(filepath):
        if row.get('排名靠前的网页'):
            result['url'] = row['排名靠前的网页']
            result['clicks'] = int(row.get('点击次数', 0) or 0)
            result['impressions'] = int(row.get('展示', 0) or 0)
            ctr_str = row.get('点击率', '0%') or '0%'
            result['ctr'] = float(ctr_str.replace('%', ''))
            result['rank'] = float(row.get('排名', 0) or 0)
            break
    return result

def _get_landing_field(row, cn_field, en_field):
    """兼容中英文表头"""
    val = row.get(cn_field, '')
    if val == '' or val is None:
        val = row.get(en_field, '')
    return val


def parse_landing_page_stats(week_folder, category):
    # ... 保持不变 ...
    result = {}
    stats_dir = BASE_PATH / 'pageviews'
    if not stats_dir.exists():
        return result
    match = re.match(r'w\d+_(\d{4}-\d{2}-\d{2})', week_folder)
    if not match:
        return result
    target_date = match.group(1)
    import glob
    pattern = str(stats_dir / f'按登陆*{target_date}.csv')
    files = glob.glob(pattern)
    if not files:
        return result
    target_file = files[0]
    target_path = f'/collections/{category}'
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                page_path = _get_landing_field(row, '登陆页面路径', 'Landing page path').strip()
                if page_path == target_path:
                    result = {
                        'sessions': int(_get_landing_field(row, '访问', 'Sessions') or 0),
                        'visitors': int(_get_landing_field(row, '在线商店访客', 'Online store visitors') or 0),
                        'bounceRate': float(_get_landing_field(row, '跳出率', 'Bounce rate') or 0),
                        'pageviewsPerSession': float(_get_landing_field(row, '每次访问的页面浏览量', 'Pageviews per session') or 0),
                        'avgSessionDuration': float(_get_landing_field(row, '平均访问持续时间', 'Average session duration') or 0),
                        'addToCart': int(_get_landing_field(row, '有商品添加到购物车的访问', 'Sessions with cart additions') or 0),
                        'checkout': int(_get_landing_field(row, '到达结账页面的访问', 'Sessions that reached checkout') or 0),
                        'purchase': int(_get_landing_field(row, '完成结账的访问', 'Sessions that completed checkout') or 0)
                    }
                    break
    except Exception as e:
        print(f"读取着陆页数据失败：{e}")
    return result

def parse_cart_adds(week_path):
    # ... 保持不变 ...
    result = []
    if not week_path.exists():
        return result
    import glob
    pattern = str(week_path / '电子商务购买_商品名称*.csv')
    files = glob.glob(pattern)
    if not files:
        return result
    target_file = files[0]
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            lines = [line for line in f if not line.strip().startswith('#') and line.strip()]
            if not lines:
                return result
            from io import StringIO
            reader = csv.DictReader(StringIO(''.join(lines)))
            for row in reader:
                product_name = row.get('商品名称', '').strip()
                if not product_name:
                    continue
                cart_adds = int(row.get('加入购物车的商品数', 0) or 0)
                if cart_adds > 0:
                    result.append({'name': product_name[:80], 'cartAdds': cart_adds})
            result.sort(key=lambda x: x['cartAdds'], reverse=True)
    except Exception as e:
        print(f"读取加购商品数据失败：{e}")
    return result

def parse_pageviews_global(week_folder, page_config=None):
    # ... 保持不变 ...
    result = {}
    pageviews_dir = BASE_PATH / 'pageviews'
    if not pageviews_dir.exists():
        return result
    match = re.match(r'w\d+_(\d{4}-\d{2}-\d{2})', week_folder)
    if not match:
        return result
    target_date = match.group(1)
    target_file = pageviews_dir / f'页面浏览数{target_date}.csv'
    if not target_file.exists():
        return result
    path_to_cat = {}
    if page_config:
        for cat, cfg in page_config.items():
            landing_page = cfg.get('landing_page', f'/collections/{cat}')
            path_to_cat[landing_page] = cat
            if cat == 'linkdolls.com':
                path_to_cat['/'] = cat
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[0].strip() and parts[0].startswith('/'):
                    path = parts[0].strip()
                    if path in path_to_cat:
                        cat = path_to_cat[path]
                        result[cat] = {'pageviews': int(parts[1] or 0), 'activeUsers': int(parts[2] or 0)}
    except Exception as e:
        print(f"读取页面浏览数失败: {e}")
    return result

def find_file(directory, keyword):
    # ... 保持不变 ...
    try:
        for f in Path(directory).iterdir():
            if f.is_file() and keyword in f.name:
                return f
    except Exception:
        pass
    return None

def aggregate_week(category, week_folder):
    # ... 保持不变（略，与原始文件相同），此处省略以节省篇幅，实际实现需保留 ...
    week_path = BASE_PATH / category / week_folder
    match = re.match(r'w(\d+)_(\d{4}-\d{2}-\d{2})', week_folder)
    week_num = int(match.group(1)) if match else 0
    date_str = match.group(2) if match else ''
    result = {
        'category': category,
        'week': f'W{week_num}',
        'weekFolder': week_folder,
        'date': date_str,
        'hasData': False,
        'gsc': {'clicks': 0, 'impressions': 0, 'ctr': 0, 'rank': 0, 'url': ''},
        'ga4': {'pageviews': 0, 'activeUsers': 0},
        'landingPage': {'sessions': 0, 'visitors': 0, 'bounceRate': 0, 'pageviewsPerSession': 0, 'avgSessionDuration': 0},
        'queries': [],
        'devices': [],
        'countries': [],
        'clicks': [],
        'conversion': {}
    }
    if not week_path.exists():
        return result
    webpage = parse_webpage(week_path / '网页.csv')
    result['gsc'] = webpage
    result['ga4'] = {'pageviews': 0, 'activeUsers': 0}
    result['queries'] = parse_queries(week_path / '查询数.csv')
    result['devices'] = parse_devices(week_path / '设备.csv')
    result['countries'] = parse_devices(week_path / '国家_地区.csv')
    result['clicks'] = parse_clicks(week_path / '页面点击数.csv')
    conv_file = find_file(week_path, '购买历程_设备类别')
    if conv_file:
        result['conversion'] = parse_conversion(conv_file)
    if result['gsc']['clicks'] > 0:
        result['hasData'] = True
    landing_data = parse_landing_page_stats(week_folder, category)
    if landing_data:
        result['landingPage'] = landing_data
    cart_data = parse_cart_adds(week_path)
    result['cartAdds'] = cart_data[:20]
    return result

# ==================== main ====================

def main():
    # 加载配置
    page_config = load_page_config()
    print(f"📋 加载配置: {len(page_config)} 个页面")
    
    # 加载全部订单
    orders_all = load_orders_all()
    
    # 收集分类
    categories = []
    for item in BASE_PATH.iterdir():
        if not item.is_dir() or item.name.startswith('.') or item.name in ['config', 'orders', 'data', 'pageviews']:
            continue
        categories.append(item.name)
    
    # 聚合数据
    all_data = {}
    weeks = set()
    
    # 先收集所有周
    for category in categories:
        cat_path = BASE_PATH / category
        for week_folder in cat_path.iterdir():
            if week_folder.is_dir() and week_folder.name.startswith('w'):
                weeks.add(week_folder.name)
    
    # 批量读取每个周的页面浏览数（所有分类共用，按精确路径匹配）
    pageviews_cache = {}
    for week in weeks:
        pageviews_cache[week] = parse_pageviews_global(week, page_config)
    
    print(f"📊 页面浏览数缓存: {len(pageviews_cache)} 周")
    
    for category in categories:
        all_data[category] = {}
        cat_path = BASE_PATH / category
        
        # 计算该分类的收入数据（按Order tag归因）
        revenue_data = calculate_revenue_by_category(orders_all, category)
        
        for week_folder in cat_path.iterdir():
            if week_folder.is_dir() and week_folder.name.startswith('w'):
                weeks.add(week_folder.name)
                data = aggregate_week(category, week_folder.name)
                
                # 注入配置
                data['config'] = page_config.get(category, {
                    'owner': '-', 
                    'q1_traffic_goal': 0, 
                    'q1_revenue_goal': 0,
                    'q2_traffic_goal': 0,
                    'q2_revenue_goal': 0,
                    'q3_traffic_goal': 0,
                    'q3_revenue_goal': 0,
                    'q4_traffic_goal': 0,
                    'q4_revenue_goal': 0
                })
                
                # 注入收入数据
                data['revenue'] = revenue_data
                
                # 从缓存注入页面浏览数（覆盖原来的空数据）
                if week_folder.name in pageviews_cache:
                    cached = pageviews_cache[week_folder.name].get(category, {})
                    if cached:
                        data['ga4'] = cached
                        if data['ga4']['pageviews'] > 0:
                            data['hasData'] = True
                
                all_data[category][week_folder.name] = data
    
    # 输出原有 dashboard_detail.json
    output = {
        'stats': {
            'categories': sorted(categories),
            'weeks': sorted(weeks),
            'totalCategories': len(categories),
            'totalWeeks': len(weeks),
            'pagesWithConfig': len(page_config)
        },
        'config': page_config,
        'data': all_data
    }
    
    output_path = BASE_PATH / 'dashboard_detail.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # ===== 新增：按产品首字母 + 按周汇总收入 =====
    week_mapping = build_week_mapping(weeks)
    prefix_weekly_revenue = calculate_category_weekly_revenue(orders_all, week_mapping)

    prefix_names = {
        'a': 'Ass 臀部', 'b': 'Boob 胸部', 'd': 'Dildo 假阳具',
        'f': 'Full Doll 完整娃', 'h': 'Head 头部', 'l': 'Legs 腿部',
        'm': 'Male 男性', 'p': 'Pussy 内部', 't': 'Torso 躯干',
        'v': 'Vajankle 足踝', 'other': 'Other 其他'
    }

    # 按周文件夹顺序生成周标签列表
    week_folders_sorted = sorted(weeks, key=lambda w: int(re.match(r'w(\d+)', w).group(1)))
    _pat = re.compile(r'w(\d+)')
    week_labels = ['W' + str(int(_pat.match(w).group(1))) for w in week_folders_sorted]

    cat_data_categories = []
    for prefix in sorted(prefix_weekly_revenue.keys()):
        weekly_data = prefix_weekly_revenue[prefix]
        weekly_orders = [weekly_data.get(w, {}).get('orders', 0) for w in week_labels]
        weekly_rev = [round(weekly_data.get(w, {}).get('revenue', 0), 2) for w in week_labels]

        cat_data_categories.append({
            'key': prefix,
            'name': prefix_names.get(prefix, prefix.upper()),
            'weeklyRevenue': weekly_rev,
            'weeklyOrders': weekly_orders,
            'totalRevenue': round(sum(weekly_rev), 2),
            'totalOrders': sum(weekly_orders)
        })

    cat_output = {
        'weeks': week_labels,
        'categories': cat_data_categories,
        'weekMapping': {w: list(week_mapping.get(w, ('', ''))) for w in week_labels}
    }

    cat_output_path = BASE_PATH / 'category_revenue.json'
    with open(cat_output_path, 'w', encoding='utf-8') as f:
        json.dump(cat_output, f, ensure_ascii=False, indent=2)

    # 统计
    with_data = sum(1 for cat in all_data.values() for w in cat.values() if w['hasData'])
    with_revenue = sum(1 for cat in all_data.values() for w in cat.values() 
                       if any(w.get('revenue', {}).get(q, {}).get('orders', 0) > 0 for q in ['Q1','Q2','Q3','Q4']))
    
    print(f"\n✅ 聚合完成！")
    print(f"   分类数: {len(categories)}")
    print(f"   周数: {len(weeks)}")
    print(f"   有流量数据: {with_data}")
    print(f"   有收入数据: {with_revenue}")
    print(f"   输出 dashboard_detail.json: {output_path}")
    print(f"   输出 category_revenue.json: {cat_output_path}")

if __name__ == '__main__':
    main()