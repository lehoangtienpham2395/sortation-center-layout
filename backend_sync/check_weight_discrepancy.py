import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

dates = {}
for row in data:
    if row.get('Trng thi') == 'Inbound':
        date = row.get('Ngy vn hnh_Inbound')
        if not date:
            continue
        vol = int(row.get('Volume') or 0)
        wt = float(row.get('Weight') or 0.0)
        if date not in dates:
            dates[date] = {'vol': 0, 'weight': 0.0}
        dates[date]['vol'] += vol
        dates[date]['weight'] += wt

print("=== INBOUND VOLUME & WEIGHT BY DATE ===")
for d, stats in sorted(dates.items()):
    avg = stats['weight'] / stats['vol'] if stats['vol'] > 0 else 0
    print(f"Ngày: {d} | Đơn: {stats['vol']:,} | Cân: {stats['weight']:,.2f} kg | TB: {avg:.2f} kg")
