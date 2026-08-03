import json
import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = os.path.join(r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0")

with open(os.path.join(BASE_DIR, 'public', 'data', 'inventory.json'), 'r', encoding='utf-8') as f:
    inv = json.load(f)

sm = {}
for r in inv:
    aid = r.get('area_id')
    st = r.get('station_name')
    vol = int(r.get('volume') or 0)
    wt = float(r.get('weight_ton') or 0)
    cap = int(r.get('capacity') or (1400 if aid == 'A06' else 780))
    if aid not in sm:
        sm[aid] = {'area_id': aid, 'buuCuc': st, 'volume': 0, 'weight': 0.0, 'capacity': cap}
    sm[aid]['volume'] += vol
    sm[aid]['weight'] += wt

sorted_list = sorted(sm.values(), key=lambda x: x['volume'], reverse=True)

out_fp = os.path.join(ARTIFACT_DIR, 'danh_sach_tat_ca_buu_cuc_volume_01082026.csv')
with open(out_fp, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Chute', 'Tên Bưu cục', 'Sản lượng Tồn (Đơn)', 'Trọng lượng (Tấn)', 'Sức chứa (Capacity)', '% Volume (% Lấp đầy)'])
    for i, r in enumerate(sorted_list, 1):
        pct = f"{round((r['volume'] / r['capacity']) * 100)}%" if r['capacity'] > 0 else '0%'
        writer.writerow([i, r['area_id'], r['buuCuc'], r['volume'], round(r['weight'], 3), r['capacity'], pct])

print(f"Exported full list CSV to {out_fp}")
