#!/usr/bin/env python3
"""
生成分类页季度目标完成汇总报表
"""
import json
import os

# 加载数据
with open('dashboard_detail.json', 'r', encoding='utf-8') as f:
    RAW = json.load(f)

# 季度定义（2026年）
QUARTERS = {
    'Q1': {'months': ['01', '02', '03'], 'weeks': []},
    'Q2': {'months': ['04', '05', '06'], 'weeks': []},
    'Q3': {'months': ['07', '08', '09'], 'weeks': []},
    'Q4': {'months': ['10', '11', '12'], 'weeks': []},
}

# 分类页名称映射
CAT_NAMES = {
    'full-doll': 'Full Doll 完整娃',
    'robotic-sex-doll': 'Robotic Sex Doll',
    'linkdolls.com': 'Linkdolls.com',
    'all': 'All',
    'bbw-sex-doll-torso': 'BBW Sex Doll Torso',
    'sex-doll-head': 'Sex Doll Head',
    'shemale-sex-doll-torso-1': 'Shemale Sex Doll Torso',
    'sex-doll-videos': 'Sex Doll Videos',
    'celebrity-sex-dolls': 'Celebrity Sex Dolls',
    'vajankle-foot-fetish-toys': 'Vajankle Foot Fetish',
    'flat-chest-sex-doll': 'Flat Chest Sex Doll',
    'furry-sex-doll': 'Furry Sex Doll',
    'in-stock-usa': 'In Stock USA',
    'femboys-sex-doll': 'Femboys Sex Doll',
    'black-torso': 'Black Torso',
    'ros-sex-doll-heads-1': 'ROS Sex Doll Heads',
    'anime-sex-doll': 'Anime Sex Doll',
    'sex-doll-torso': 'Sex Doll Torso',
    'big-boobs-sex-doll': 'Big Boobs Sex Doll',
    'under-1000-full-doll': 'Under $1000 Full Doll',
    'new-arrivals': 'New Arrivals',
    'sex-doll-torso-dildo-for-woman': 'Sex Doll Torso Dildo',
    'fake-ass-sex-toy': 'Fake Ass Sex Toy',
    'best-sex-doll': 'Best Sex Doll',
    'hyper-realistic-sex-doll': 'Hyper Realistic Sex Doll',
    'cheap-sex-dolls': 'Cheap Sex Dolls',
}

def get_cat_name(cat_key):
    return CAT_NAMES.get(cat_key, cat_key.replace('-', ' ').title())

def calc_quarterly_actual(cat_data, quarter):
    """计算某分类页某季度的实际流量和销售额"""
    months = QUARTERS[quarter]['months']
    total_uv = 0
    total_revenue = 0
    revenue_found = False

    for week_key, week_data in cat_data.items():
        if not week_key.startswith('w'):
            continue
        # 从周文件夹名提取日期，判断属于哪个月
        # week_key 格式: w19_2026-05-04
        parts = week_key.split('_')
        if len(parts) < 2:
            continue
        date_str = parts[1]  # 2026-05-04
        month = date_str.split('-')[1]

        if month in months:
            ga4 = week_data.get('ga4', {})
            total_uv += ga4.get('activeUsers', 0)
            # 销售额：revenue 是季度累计值，只取一次
            if not revenue_found:
                rev = week_data.get('revenue', {}).get(quarter, {})
                total_revenue = rev.get('totalSales', 0)
                revenue_found = True

    return total_uv, total_revenue

# 汇总所有分类页数据
report = []
for cat_key, cat_config in RAW['config'].items():
    cat_data = RAW['data'].get(cat_key, {})
    row = {
        'category': cat_key,
        'name': get_cat_name(cat_key),
        'owner': cat_config.get('owner', ''),
        'quarters': {}
    }

    for q in ['Q1', 'Q2', 'Q3', 'Q4']:
        target_uv = cat_config.get(f'{q.lower()}_traffic_goal', 0)
        target_rev = cat_config.get(f'{q.lower()}_revenue_goal', 0)
        actual_uv, actual_rev = calc_quarterly_actual(cat_data, q)

        row['quarters'][q] = {
            'target_uv': target_uv,
            'actual_uv': actual_uv,
            'uv_rate': round(actual_uv / target_uv * 100, 1) if target_uv > 0 else 0,
            'target_rev': target_rev,
            'actual_rev': actual_rev,
            'rev_rate': round(actual_rev / target_rev * 100, 1) if target_rev > 0 else 0,
        }

    report.append(row)

# 按Q2完成率排序
report.sort(key=lambda x: x['quarters']['Q2']['rev_rate'], reverse=True)

# 保存JSON
with open('quarterly_report_data.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"✓ 已生成 quarterly_report_data.json ({len(report)} 个分类页)")

# 生成HTML报表
html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分类页季度目标完成汇总 | LinkDolls</title>
<style>
:root {
  --bg: #0f172a; --card: #1e293b; --text: #f1f5f9;
  --muted: #94a3b8; --border: #334155;
  --green: #10b981; --red: #ef4444; --yellow: #f59e0b;
  --blue: #3b82f6; --purple: #8b5cf6;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg); color: var(--text); padding: 24px;
}
.header {
  display:flex; justify-content:space-between; align-items:center;
  margin-bottom: 24px; flex-wrap:wrap; gap:12px;
}
.header h1 { font-size: 24px; font-weight: 700; }
.header .subtitle { color: var(--muted); font-size: 14px; margin-top: 4px; }
.quarter-tabs {
  display:flex; gap: 8px;
}
.quarter-tab {
  padding: 8px 20px; border-radius: 8px; cursor: pointer;
  background: var(--card); border: 1px solid var(--border);
  font-size: 14px; font-weight: 600; transition: all 0.2s;
}
.quarter-tab.active {
  background: var(--blue); border-color: var(--blue);
}
.quarter-tab:hover:not(.active) { border-color: var(--blue); }

.table-wrap {
  background: var(--card); border-radius: 12px;
  border: 1px solid var(--border); overflow: hidden;
}
table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
th {
  background: rgba(59,130,246,0.1); color: var(--blue);
  font-weight: 600; text-align: left; padding: 14px 12px;
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
td {
  padding: 12px; border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
tr:hover td { background: rgba(59,130,246,0.05); }
.cat-name { font-weight: 600; }
.cat-key { color: var(--muted); font-size: 11px; margin-top: 2px; }
.owner { color: var(--muted); font-size: 12px; }

.num { font-family: 'SF Mono', monospace; font-weight: 600; }
.rate {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 700;
}
.rate.high { background: rgba(16,185,129,0.15); color: var(--green); }
.rate.mid { background: rgba(245,158,11,0.15); color: var(--yellow); }
.rate.low { background: rgba(239,68,68,0.15); color: var(--red); }

.progress-bar {
  width: 80px; height: 6px; background: var(--border);
  border-radius: 3px; overflow: hidden; margin-top: 4px;
}
.progress-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, var(--blue), var(--purple));
}
.progress-fill.high { background: var(--green); }
.progress-fill.mid { background: var(--yellow); }
.progress-fill.low { background: var(--red); }

.summary-row {
  background: rgba(59,130,246,0.08) !important;
  font-weight: 700;
}
.summary-row td { border-top: 2px solid var(--blue); }

.footer {
  margin-top: 20px; color: var(--muted); font-size: 12px;
  text-align: center;
}

@media (max-width: 768px) {
  body { padding: 12px; }
  th, td { padding: 8px 6px; font-size: 12px; }
  .hide-mobile { display: none; }
}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>📊 分类页季度目标完成汇总</h1>
    <div class="subtitle">数据来源：GSC · GA4 · Shopify | 目标完成率 = 实际值 ÷ 目标值</div>
  </div>
  <div class="quarter-tabs">
    <div class="quarter-tab active" data-q="Q2">Q2</div>
    <div class="quarter-tab" data-q="Q1">Q1</div>
    <div class="quarter-tab" data-q="Q3">Q3</div>
    <div class="quarter-tab" data-q="Q4">Q4</div>
  </div>
</div>

<div class="table-wrap">
  <table id="reportTable">
    <thead>
      <tr>
        <th>分类页</th>
        <th>负责人</th>
        <th style="text-align:right">流量目标 (UV)</th>
        <th style="text-align:right">实际流量</th>
        <th style="text-align:center">完成率</th>
        <th style="text-align:right">销售目标 ($)</th>
        <th style="text-align:right">实际销售</th>
        <th style="text-align:center">完成率</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<div class="footer">
  点击上方 Q1/Q2/Q3/Q4 切换季度查看 | 绿色=达标(≥80%) 黄色=接近(50-80%) 红色=落后(<50%)
</div>

<script>
const DATA = ''' + json.dumps(report, ensure_ascii=False) + ''';
const QUARTERS = ['Q1','Q2','Q3','Q4'];
let currentQ = 'Q2';

function fmtNum(n) {
  if (n === 0) return '0';
  return n.toLocaleString();
}
function fmtMoney(n) {
  if (n === 0) return '$0';
  return '$' + n.toLocaleString();
}
function rateClass(rate) {
  if (rate >= 80) return 'high';
  if (rate >= 50) return 'mid';
  return 'low';
}

function render() {
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';

  let sumTargetUV = 0, sumActualUV = 0;
  let sumTargetRev = 0, sumActualRev = 0;

  DATA.forEach(row => {
    const q = row.quarters[currentQ];
    sumTargetUV += q.target_uv;
    sumActualUV += q.actual_uv;
    sumTargetRev += q.target_rev;
    sumActualRev += q.actual_rev;

    const uvRateClass = rateClass(q.uv_rate);
    const revRateClass = rateClass(q.rev_rate);

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="cat-name">${row.name}</div>
        <div class="cat-key">${row.category}</div>
      </td>
      <td class="owner">${row.owner || '-'}</td>
      <td style="text-align:right" class="num">${fmtNum(q.target_uv)}</td>
      <td style="text-align:right" class="num">${fmtNum(q.actual_uv)}</td>
      <td style="text-align:center">
        <span class="rate ${uvRateClass}">${q.uv_rate}%</span>
        <div class="progress-bar">
          <div class="progress-fill ${uvRateClass}" style="width:${Math.min(q.uv_rate,100)}%"></div>
        </div>
      </td>
      <td style="text-align:right" class="num">${fmtMoney(q.target_rev)}</td>
      <td style="text-align:right" class="num">${fmtMoney(q.actual_rev)}</td>
      <td style="text-align:center">
        <span class="rate ${revRateClass}">${q.rev_rate}%</span>
        <div class="progress-bar">
          <div class="progress-fill ${revRateClass}" style="width:${Math.min(q.rev_rate,100)}%"></div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // 汇总行
  const uvRate = sumTargetUV > 0 ? Math.round(sumActualUV / sumTargetUV * 100) : 0;
  const revRate = sumTargetRev > 0 ? Math.round(sumActualRev / sumTargetRev * 100) : 0;
  const uvRateClass = rateClass(uvRate);
  const revRateClass = rateClass(revRate);

  const summary = document.createElement('tr');
  summary.className = 'summary-row';
  summary.innerHTML = `
    <td colspan="2"><strong>📈 全站合计</strong></td>
    <td style="text-align:right" class="num">${fmtNum(sumTargetUV)}</td>
    <td style="text-align:right" class="num">${fmtNum(sumActualUV)}</td>
    <td style="text-align:center">
      <span class="rate ${uvRateClass}">${uvRate}%</span>
      <div class="progress-bar">
        <div class="progress-fill ${uvRateClass}" style="width:${Math.min(uvRate,100)}%"></div>
      </div>
    </td>
    <td style="text-align:right" class="num">${fmtMoney(sumTargetRev)}</td>
    <td style="text-align:right" class="num">${fmtMoney(sumActualRev)}</td>
    <td style="text-align:center">
      <span class="rate ${revRateClass}">${revRate}%</span>
      <div class="progress-bar">
        <div class="progress-fill ${revRateClass}" style="width:${Math.min(revRate,100)}%"></div>
      </div>
    </td>
  `;
  tbody.appendChild(summary);
}

// Tab切换
document.querySelectorAll('.quarter-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.quarter-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentQ = tab.dataset.q;
    render();
  });
});

render();
</script>
</body>
</html>
'''

with open('dashboard_quarterly.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✓ 已生成 dashboard_quarterly.html")
print(f"\n预览 ({len(report)} 个分类页):")
print("-" * 80)
for row in report[:5]:
    q2 = row['quarters']['Q2']
    print(f"{row['name'][:30]:<30} | 流量: {q2['actual_uv']}/{q2['target_uv']} ({q2['uv_rate']}%) | 销售: ${q2['actual_rev']:.0f}/${q2['target_rev']:.0f} ({q2['rev_rate']}%)")
