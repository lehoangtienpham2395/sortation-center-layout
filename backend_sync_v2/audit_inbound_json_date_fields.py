import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

rows = data if isinstance(data, list) else data.get('data', [])

print(f"Total rows in data/inbound.json: {len(rows)}")

op_created_set = set()
op_pickup_set = set()
op_arrival_set = set()

for r in rows[:100]:
    c = r.get('op_date_created') or r.get('Ngày vận hành_Created') or r.get('op_date_forecast')
    p = r.get('op_date_pickup') or r.get('Ngày vận hành_Pickup')
    a = r.get('op_date_arrival') or r.get('Ngày vận hành_Arrival')
    if c: op_created_set.add(str(c))
    if p: op_pickup_set.add(str(p))
    if a: op_arrival_set.add(str(a))

print("Sample op_date_created:", list(op_created_set)[:10])
print("Sample op_date_pickup:", list(op_pickup_set)[:10])
print("Sample op_date_arrival:", list(op_arrival_set)[:10])

# Count rows matching 2026-08-03 across all fields
count_2026_08_03 = 0
for r in rows:
    c = str(r.get('op_date_created') or r.get('Ngày vận hành_Created') or r.get('op_date_forecast') or '')
    p = str(r.get('op_date_pickup') or r.get('Ngày vận hành_Pickup') or '')
    a = str(r.get('op_date_arrival') or r.get('Ngày vận hành_Arrival') or '')
    if '2026-08-03' in c or '2026-08-03' in p or '2026-08-03' in a:
        count_2026_08_03 += 1

print(f"\nRows matching '2026-08-03' in data/inbound.json: {count_2026_08_03}")
