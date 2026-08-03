import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inventory.json', 'r', encoding='utf-8') as f:
    inventory = json.load(f)

selected_map = {}
for item in inventory:
    key = item.get('area_id')
    if not key: continue
    wt_raw = item.get('weight_ton') if item.get('weight_ton') is not None else item.get('weight')
    wt = float(wt_raw or 0)
    vol = int(item.get('volume') or 0)
    if key not in selected_map:
        selected_map[key] = {'volume': 0, 'weight': 0.0}
    selected_map[key]['volume'] += vol
    selected_map[key]['weight'] += wt

print('Sample selectedMap entries:')
for k, v in list(selected_map.items())[:10]:
    wt_val = v['weight']
    display_wt = f"{wt_val:.3f}" if (wt_val > 0 and wt_val < 0.1) else f"{wt_val:.1f}"
    print(f" - Area {k}: volume={v['volume']}, weight={v['weight']:.4f} Tấn -> Display string: '{display_wt} Tấn'")
