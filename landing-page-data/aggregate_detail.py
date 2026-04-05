#!/usr/bin/env python3
"""
完整数据聚合脚本
- 读取各分类页的周数据（GSC/GA4等）
- 读取config/pages.csv（目标、负责人）
- 读取data/orders/orders_2026_Q1.csv（订单数据，按Order tag归因）
"""

import os
import json
from pathlib import Path
import csv
import re
from collections import defaultdict

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
            # /collections/bbw-sex-doll-torso -> bbw-sex-doll-torso
            # /linkdolls.com -> linkdolls.com (首页)
            if url.startswith('/collections/'):
                cat = url.replace('/collections/', '')
            elif url == '/linkdolls.com':
                cat = 'homepage'
            elif url.startswith('/pages/'):
                cat = url.replace('/pages/', '')
            else:
                cat = url.strip('/')
            
            config[cat] = {
                'owner': row.get('负责人', '-').strip(),
                'q1_traffic_goal': int(float(row.get('q1流量目标', 0) or 0)),
                'q1_revenue_goal': int(float(str(row.get('q1销售金额', 0) or '0').replace('$', '').replace(',', '').replace(' ', '')))
            }
    
    print(f"📋 加载配置: {len(config)} 个页面")
    return config

def load_orders_all():
    """读取全部订单数据"""
    orders_path = Path('/Users/apple/Desktop/linkdolls dashboard/orders/orders_detail_2026_Q1_with_tags.csv')
    
    if not orders_path.exists():
        print(f"订单文件不存在: {orders_path}")
        return []
    
    orders = []
    with open(orders_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            orders.append(row)
    
    print(f"📦 加载订单: {len(orders)} 行")
    return orders

def calculate_revenue_by_category(orders_all, category):
    """按页面归因计算收入数据"""
    # 构造url_path - 需要匹配 Order tag
    # Order tag 格式可能是：/collections/bbw-sex-doll-torso 或其他
    url_path = f"/collections/{category}"
    if category == 'homepage':
        url_path = '/linkdolls.com'
    
    # 筛选：Order tag 匹配
    filtered = [o for o in orders_all if o.get('Order tag', '').strip() == url_path]
    
    if not filtered:
        return {
            'orders': 0,
            'totalSales': 0,
            'avgPrice': 0,
            'products': [],
            'monthlySales': {'01': 0, '02': 0, '03': 0}
        }
    
    # Q1累计销售额 = Net sales 加总
    total_sales = sum(float(o.get('Net sales', 0) or 0) for o in filtered)
    
    # Q1累计订单数 = Order name 去重
    unique_orders = set(o.get('Order name', '') for o in filtered)
    order_count = len(unique_orders)
    
    # 均单价
    avg_price = round(total_sales / order_count, 2) if order_count > 0 else 0
    
    # 产品明细：按 Product title 分组，剔除 Shipping
    product_sales = defaultdict(lambda: {'orders': 0, 'sales': 0})
    for o in filtered:
        product_title = o.get('Product title', '').strip()
        if 'Shipping' in product_title:
            continue
        net_sales = float(o.get('Net sales', 0) or 0)
        product_sales[product_title]['orders'] += 1
        product_sales[product_title]['sales'] += net_sales
    
    # 按销售额降序，取前10
    products = sorted(
        [{'name': k, 'orders': v['orders'], 'sales': round(v['sales'], 2)} for k, v in product_sales.items()],
        key=lambda x: x['sales'],
        reverse=True
    )[:10]
    
    # 月度销售趋势
    monthly_sales = defaultdict(float)
    for o in filtered:
        day = o.get('Day', '').strip()
        if len(day) >= 7:
            month = day[5:7]  # MM
            if month in ['01', '02', '03']:
                monthly_sales[month] += float(o.get('Net sales', 0) or 0)
    
    return {
        'orders': order_count,
        'totalSales': round(total_sales, 2),
        'avgPrice': avg_price,
        'products': products,
        'monthlySales': {
            '01': round(monthly_sales.get('01', 0), 2),
            '02': round(monthly_sales.get('02', 0), 2),
            '03': round(monthly_sales.get('03', 0), 2)
        }
    }

def parse_clicks_global(week_folder):
    """从统一目录读取页面元素点击数"""
    result = []
    clicks_dir = BASE_PATH / 'clicks'
    
    if not clicks_dir.exists():
        return result
    
    # 从周文件夹提取日期
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
                    
                    result.append({
                        'rank': rank,
                        'type': 'f' if is_filter else 'p',
                        'name': name,
                        'clicks': events,
                        'url': url
                    })
    except Exception as e:
        print(f"读取页面元素点击数失败: {e}")
    
    return result

def parse_clicks(filepath):
    """解析页面元素点击数.csv"""
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
                    # 判断类型：筛选 (?) / 产品 (products) / 导航 (collections)
                    # 优先级：1.筛选器 (带？参数)  2.产品  3.导航
                    if '?' in url and '/products/' not in url:
                        # 带参数且不是产品页 = 筛选器
                        link_type = 'f'  # filter 筛选
                        name = "筛选：" + url.split('?')[-1][:25]
                    elif '/products/' in url:
                        link_type = 'p'  # product 产品
                        name = "产品：" + url.split('/products/')[-1].split('?')[0][:35]
                    elif '/collections/' in url:
                        link_type = 'n'  # navigation 导航
                        name = "导航：" + url.split('/collections/')[-1].split('?')[0][:35]
                    else:
                        link_type = 'n'  # 默认导航
                        name = url.split('//')[-1][:35]

                    clicks.append({
                        'rank': rank,
                        'type': link_type,
                        'name': name,
                        'clicks': events,
                        'url': url
                    })
    except:
        pass
    return clicks

def parse_conversion(filepath):
    """解析购买历程_设备类别.csv"""
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
    """解析设备.csv"""
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
    """解析查询数.csv"""
    queries = []
    for row in parse_csv(filepath):
        if row.get('热门查询'):
            rank = float(row.get('排名', 999) or 999)
            clicks = int(row.get('点击次数', 0) or 0)
            ctr_str = row.get('点击率', '0%') or '0%'
            ctr = float(ctr_str.replace('%', ''))
            
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
            
            queries.append({
                'kw': row['热门查询'],
                'rank': round(rank, 2),
                'clicks': clicks,
                'imp': int(row.get('展示', 0) or 0),
                'ctr': round(ctr, 1),
                'tag': tag
            })
    return queries

def parse_webpage(filepath):
    """解析网页.csv"""
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

def parse_landing_page_stats(week_folder, category):
    """解析按登陆页面划分的访问量 - 加购 - 结账 - 转化.csv"""
    result = {}
    stats_dir = BASE_PATH / 'pageviews'
    
    if not stats_dir.exists():
        return result
    
    # 从周文件夹提取日期
    match = re.match(r'w\d+_(\d{4}-\d{2}-\d{2})', week_folder)
    if not match:
        return result
    
    target_date = match.group(1)
    # 使用 glob 匹配文件（文件名可能有空格变化）
    import glob
    pattern = str(stats_dir / f'按登陆*{target_date}.csv')
    files = glob.glob(pattern)
    
    if not files:
        return result
    
    target_file = files[0]
    
    # 构建当前分类的着陆页路径（精确匹配）
    target_path = f'/collections/{category}'
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                page_path = row.get('登陆页面路径', '').strip()
                # 精确匹配着陆页
                if page_path == target_path:
                    result = {
                        'sessions': int(row.get('访问', 0) or 0),
                        'visitors': int(row.get('在线商店访客', 0) or 0),
                        'bounceRate': float(row.get('跳出率', 0) or 0),
                        'pageviewsPerSession': float(row.get('每次访问的页面浏览量', 0) or 0),
                        'avgSessionDuration': float(row.get('平均访问持续时间', 0) or 0),
                        'addToCart': int(row.get('有商品添加到购物车的访问', 0) or 0),
                        'checkout': int(row.get('到达结账页面的访问', 0) or 0),
                        'purchase': int(row.get('完成结账的访问', 0) or 0)
                    }
                    break
    except Exception as e:
        print(f"读取着陆页数据失败：{e}")
    
    return result

def parse_cart_adds(week_path):
    """解析电子商务购买_商品名称*.csv - 加购商品列表"""
    result = []
    
    if not week_path.exists():
        return result
    
    # 在周文件夹内查找匹配的文件
    import glob
    pattern = str(week_path / '电子商务购买_商品名称*.csv')
    files = glob.glob(pattern)
    
    if not files:
        return result
    
    target_file = files[0]
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            # 先读取所有行，跳过注释
            lines = [line for line in f if not line.strip().startswith('#') and line.strip()]
            
            if not lines:
                return result
            
            # 解析 CSV
            import csv
            from io import StringIO
            reader = csv.DictReader(StringIO(''.join(lines)))
            
            for row in reader:
                product_name = row.get('商品名称', '').strip()
                if not product_name:
                    continue
                    
                cart_adds = int(row.get('加入购物车的商品数', 0) or 0)
                
                if cart_adds > 0:
                    result.append({
                        'name': product_name[:80],  # 限制长度
                        'cartAdds': cart_adds
                    })
            
            # 按加购数降序排序
            result.sort(key=lambda x: x['cartAdds'], reverse=True)
    except Exception as e:
        print(f"读取加购商品数据失败：{e}")
    
    return result

def parse_pageviews_global(week_folder, page_config=None):
    """从统一目录读取页面浏览数（按配置的精确路径匹配）"""
    result = {}
    pageviews_dir = BASE_PATH / 'pageviews'
    
    if not pageviews_dir.exists():
        return result
    
    # 从周文件夹提取日期（w13_2026-03-23 -> 2026-03-23）
    match = re.match(r'w\d+_(\d{4}-\d{2}-\d{2})', week_folder)
    if not match:
        return result
    
    target_date = match.group(1)
    
    # 查找匹配的文件（页面浏览数2026-03-23.csv）
    target_file = pageviews_dir / f'页面浏览数{target_date}.csv'
    
    if not target_file.exists():
        return result
    
    # 构建路径到分类的映射（只匹配配置中定义的路径）
    path_to_cat = {}
    if page_config:
        for cat, cfg in page_config.items():
            landing_page = cfg.get('landing_page', f'/collections/{cat}')
            path_to_cat[landing_page] = cat
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[0].strip() and parts[0].startswith('/'):
                    path = parts[0].strip()
                    
                    # 精确路径匹配：只处理配置中定义的路径
                    if path in path_to_cat:
                        cat = path_to_cat[path]
                    
                        result[cat] = {
                            'pageviews': int(parts[1] or 0),
                            'activeUsers': int(parts[2] or 0)
                        }
    except Exception as e:
        print(f"读取页面浏览数失败: {e}")
    
    return result

def aggregate_week(category, week_folder):
    """聚合单周数据"""
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
    
    # 页面浏览数现在从统一目录读取，在main函数中注入
    result['ga4'] = {'pageviews': 0, 'activeUsers': 0}
    
    result['queries'] = parse_queries(week_path / '查询数.csv')
    result['devices'] = parse_devices(week_path / '设备.csv')
    result['countries'] = parse_devices(week_path / '国家_地区.csv')
    result['clicks'] = parse_clicks(week_path / '页面点击数.csv')
    result['conversion'] = parse_conversion(week_path / '购买历程_设备类别.csv')
    
    if result['gsc']['clicks'] > 0:
        result['hasData'] = True
    
    # 添加着陆页数据
    landing_data = parse_landing_page_stats(week_folder, category)
    if landing_data:
        result['landingPage'] = landing_data
    
    # 添加加购商品数据
    cart_data = parse_cart_adds(week_path)
    result['cartAdds'] = cart_data[:20]  # 取前 20 个
    
    return result

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
                    'q1_revenue_goal': 0
                })
                
                # 注入收入数据
                data['revenue'] = revenue_data
                
                # 从缓存注入页面浏览数（覆盖原来的空数据）
                if week_folder.name in pageviews_cache:
                    cached = pageviews_cache[week_folder.name].get(category, {})
                    if cached:
                        data['ga4'] = cached
                        # 更新 hasData 标志
                        if data['ga4']['pageviews'] > 0:
                            data['hasData'] = True
                
                all_data[category][week_folder.name] = data
    
    # 输出JSON
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
    
    # 统计
    with_data = sum(1 for cat in all_data.values() for w in cat.values() if w['hasData'])
    with_revenue = sum(1 for cat in all_data.values() for w in cat.values() if w.get('revenue', {}).get('orders', 0) > 0)
    
    print(f"\n✅ 聚合完成！")
    print(f"   分类数: {len(categories)}")
    print(f"   周数: {len(weeks)}")
    print(f"   有流量数据: {with_data}")
    print(f"   有收入数据: {with_revenue}")
    print(f"   输出: {output_path}")

if __name__ == '__main__':
    main()