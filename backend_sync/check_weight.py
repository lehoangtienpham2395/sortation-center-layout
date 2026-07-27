import json, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('public/data/inbound.json', 'r', encoding='utf-8'))
arr = data if isinstance(data, list) else (data.get('pivot_data') or data.get('data') or [])
target = '2026-07-27'

# All fields in first record
r0 = arr[0]
print('=== ALL FIELDS first record ===')
for k, v in r0.items():
    print(f'  [{k}] = {repr(v)}')
print()

# Top stations by inbound today
station_stats = defaultdict(lambda: {'vol': 0, 'wt': 0})
for r in arr:
    if (r.get('Trng thi') or '') != 'Inbound':
        continue
    if (r.get('Ngy vn hnh_Inbound') or '') != target:
        continue
    st = (r.get('Bu cc') or 'UNKNOWN').strip().upper()
    vol = int(r.get('Volume') or 1)
    wt  = float(r.get('Weight') or 0)
    station_stats[st]['vol'] += vol
    station_stats[st]['wt']  += wt

print('Top 5 stations (Inbound today):')
sorted_st = sorted(station_stats.items(), key=lambda x: x[1]['vol'], reverse=True)[:5]
for st, v in sorted_st:
    wt_kg  = v['wt']
    wt_tan = v['wt'] / 1000.0
    print(f'  {st}: vol={v["vol"]:,} | raw_wt={wt_kg:.2f} | /1000={wt_tan:.4f} Tan')

total_vol = sum(v['vol'] for v in station_stats.values())
total_wt  = sum(v['wt']  for v in station_stats.values())
print(f'\nTOTAL: {total_vol:,} orders | {total_wt:.2f} raw | {total_wt/1000:.3f} Tan')

# Check Loi rt / Loai rot field + date logic
print()
print('=== LOAI ROT vs DATE CHECK ===')
rot_dist = defaultdict(int)
date_compare = {'fcDate < activeDate AND loiRot=hom_nay': 0,
                'fcDate < activeDate AND loiRot=hom_truoc': 0,
                'fcDate == activeDate AND loiRot=hom_nay': 0,
                'fcDate == activeDate AND no_loiRot': 0,
                'fcDate < activeDate AND no_loiRot': 0}

for r in arr:
    status = r.get('Trng thi') or ''
    if status != 'Created':
        continue
    fc_date = r.get('Ngy vn hnh_Forecast') or r.get('Ngay van hanh_Forecast') or ''
    if not fc_date:
        continue
    fc_date = str(fc_date)[:10]
    if fc_date > target:
        continue
    loi_rot = r.get('Loi rt') or r.get('Loại rớt') or ''
    has_hub = bool(r.get('Ngy vn hnh_Inbound') or r.get('Ngy vn hnh_Arrival') or
                   status in ('Outbound', 'Inbound', 'Transporting'))
    if has_hub:
        continue
    vol = int(r.get('Volume') or 1)

    if fc_date < target and loi_rot == 'Rớt hôm nay':
        date_compare['fcDate < activeDate AND loiRot=hom_nay'] += vol
    elif fc_date < target and loi_rot == 'Rớt hôm trước':
        date_compare['fcDate < activeDate AND loiRot=hom_truoc'] += vol
    elif fc_date == target and loi_rot == 'Rớt hôm nay':
        date_compare['fcDate == activeDate AND loiRot=hom_nay'] += vol
    elif fc_date == target and not loi_rot:
        date_compare['fcDate == activeDate AND no_loiRot'] += vol
    elif fc_date < target and not loi_rot:
        date_compare['fcDate < activeDate AND no_loiRot'] += vol

for k, v in date_compare.items():
    print(f'  {k}: {v:,}')
