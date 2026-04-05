#!/usr/bin/env python3
"""
聚合所有分类页周数据，生成 dashboard_data.json
空文件夹也会记录，前端显示"未导入数据"
"""

import os
import json
from pathlib import Path
import csv

BASE_PATH = Path(__file__).parent.resolve()

def parse_csv(filepath):
    """解析CSV文件"""
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(dict(row))
    except Exception as e:
        pass
    return data

def safe_contains(text, substr):
    """安全检查字符串是否包含子串"""
    return substr in str(text) if text else False

def aggregate_week(category, week_folder):
    """聚合单个分类+周的数据"""
    week_path = BASE_PATH / category / week_folder
    
    result = {
        'url': f'/collections/{category}',
        'category': category,
        'week': week_folder,
        'pageviews': 0,
        'activeUsers': 0,
        'clicks': 0,
        'impressions': 0,
        'ctr': 0,
        'avgRank': 0,
        'status': 'pending',  # pending = 未导入数据
        'createdAt': week_folder.split('_')[1] if '_' in week_folder else '-',
        'hasData': False,
        
        # 详情数据
        'devices': [],
        'countries': [],
        'queries': [],
        'topPages': [],
        'conversion': {}
    }
    
    if not week_path.exists():
        return result
    
    # 检查是否有数据文件
    csv_files = list(week_path.glob('*.csv'))
    if not csv_files:
        return result
    
    # 网页.csv
    webpage_data = parse_csv(week_path / '网页.csv')
    for row in webpage_data:
        clicks = int(row.get('点击次数', 0) or 0)
        impressions = int(row.get('展示', 0) or 0)
        result['clicks'] += clicks
        result['impressions'] += impressions
        
        url = row.get('排名靠前的网页', '')
        if url:
            result['topPages'].append({
                'url': url,
                'clicks': clicks,
                'impressions': impressions,
                'ctr': row.get('点击率', '0%'),
                'rank': float(row.get('排名', 0) or 0)
            })
    
    # 设备.csv
    device_data = parse_csv(week_path / '设备.csv')
    for row in device_data:
        if row.get('设备'):
            result['devices'].append({
                'device': row['设备'],
                'clicks': int(row.get('点击次数', 0) or 0),
                'impressions': int(row.get('展示', 0) or 0),
                'ctr': row.get('点击率', '0%')
            })
    
    # 国家_地区.csv
    country_data = parse_csv(week_path / '国家_地区.csv')
    for row in country_data:
        if row.get('国家/地区'):
            result['countries'].append({
                'country': row['国家/地区'],
                'clicks': int(row.get('点击次数', 0) or 0),
                'impressions': int(row.get('展示', 0) or 0),
                'ctr': row.get('点击率', '0%'),
                'rank': float(row.get('排名', 0) or 0)
            })
    
    # 查询数.csv
    query_data = parse_csv(week_path / '查询数.csv')
    for row in query_data:
        if row.get('热门查询'):
            result['queries'].append({
                'query': row['热门查询'],
                'clicks': int(row.get('点击次数', 0) or 0),
                'impressions': int(row.get('展示', 0) or 0),
                'ctr': row.get('点击率', '0%'),
                'rank': float(row.get('排名', 0) or 0)
            })
    
    # 购买历程_设备类别.csv
    conversion_data = parse_csv(week_path / '购买历程_设备类别.csv')
    for row in conversion_data:
        if row.get('设备类别'):
            result['conversion'][row['设备类别']] = {
                'sessions': int(row.get('会话开始 活跃用户', 0) or 0),
                'viewProduct': int(row.get('查看产品 活跃用户', 0) or 0),
                'addToCart': int(row.get('加入购物车 活跃用户', 0) or 0),
                'checkout': int(row.get('开始结账 活跃用户', 0) or 0),
                'purchase': int(row.get('购买 活跃用户', 0) or 0)
            }
    
    # 页面浏览数.csv - 特殊处理（有注释行）
    try:
        with open(week_path / '页面浏览数.csv', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    path = parts[0]
                    if category in path:
                        result['pageviews'] += int(parts[1] or 0)
                        result['activeUsers'] += int(parts[2] or 0)
    except:
        pass
    
    # 计算CTR
    if result['impressions'] > 0:
        result['ctr'] = round(result['clicks'] / result['impressions'] * 100, 2)
    
    # 判断是否有数据
    if result['clicks'] > 0 or result['pageviews'] > 0:
        result['hasData'] = True
        result['status'] = 'done'
    
    return result

def main():
    all_data = []
    categories = []
    weeks = set()
    
    # 先收集所有分类和所有周
    for item in BASE_PATH.iterdir():
        if not item.is_dir() or item.name.startswith('.'):
            continue
        if item.name in ['config', 'orders']:
            continue
        
        categories.append(item.name)
        
        for week_folder in item.iterdir():
            if week_folder.is_dir() and week_folder.name.startswith('w'):
                weeks.add(week_folder.name)
    
    # 生成所有分类×周的组合
    total = len(categories) * len(weeks)
    processed = 0
    with_data = 0
    
    for category in sorted(categories):
        for week in sorted(weeks):
            data = aggregate_week(category, week)
            all_data.append(data)
            processed += 1
            if data['hasData']:
                with_data += 1
    
    # 输出JSON
    output = {
        'stats': {
            'totalRecords': len(all_data),
            'totalPageviews': sum(d['pageviews'] for d in all_data),
            'totalClicks': sum(d['clicks'] for d in all_data),
            'totalImpressions': sum(d['impressions'] for d in all_data),
            'categories': sorted(categories),
            'weeks': sorted(weeks),
            'withData': with_data,
            'withoutData': len(all_data) - with_data
        },
        'records': all_data
    }
    
    output_path = BASE_PATH / 'dashboard_data.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 完成！")
    print(f"   分类数: {len(categories)}")
    print(f"   周数: {len(weeks)}")
    print(f"   总记录: {len(all_data)}")
    print(f"   有数据: {with_data}")
    print(f"   未导入: {len(all_data) - with_data}")
    print(f"   输出: {output_path}")

if __name__ == '__main__':
    main()