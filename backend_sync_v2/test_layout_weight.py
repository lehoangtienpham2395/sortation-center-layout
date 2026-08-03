import json

with open('public/data/inventory.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

total_vol = 0
total_wt = 0.0

for item in data:
    vol = int(item.get('volume') or 0)
    wt_raw = item.get('weight_ton') if item.get('weight_ton') is not None else item.get('weight')
    wt = float(wt_raw or 0.0)
    total_vol += vol
    total_wt += wt

print(f"Inventory total volume: {total_vol} orders | total weight_ton: {total_wt:.3f} Tấn")
