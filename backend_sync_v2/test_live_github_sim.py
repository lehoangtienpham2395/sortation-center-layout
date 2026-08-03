import urllib.request
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

t = int(time.time() * 1000)

def fetch_json(st):
    url = f"https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/{st}.json?t={t}"
    req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode('utf-8'))

inventory_rows = fetch_json('inventory')
outbound_rows = fetch_json('outbound')
backlog_rows = fetch_json('backlog')

print(f"Fetched from GitHub Raw: inventory={len(inventory_rows)}, outbound={len(outbound_rows)}, backlog={len(backlog_rows)}")

# Simulate React selectedMap for 'Backlog'
selected_map_backlog = {}
for r in inventory_rows + backlog_rows:
    area = r.get('area_id')
    if not area or area == 'None': continue
    wt = float(r.get('weight_ton') or r.get('weight') or 0)
    vol = int(r.get('volume') or 0)
    if area not in selected_map_backlog:
        selected_map_backlog[area] = {'volume': 0, 'weight': 0.0, 'station_name': r.get('station_name')}
    selected_map_backlog[area]['volume'] += vol
    selected_map_backlog[area]['weight'] += wt

tot_vol = sum(v['volume'] for v in selected_map_backlog.values())
tot_wt = sum(v['weight'] for v in selected_map_backlog.values())

print(f"\n🎯 React Backlog Mode Calculation:")
print(f"Total Backlog Volume: {tot_vol:,} orders")
print(f"Total Backlog Weight: {tot_wt:.3f} Tấn")

sorted_top10 = sorted(selected_map_backlog.items(), key=lambda x: x[1]['volume'], reverse=True)[:10]
print("\nTop 10 Backlog Racks:")
for rank, (area, stats) in enumerate(sorted_top10, 1):
    wt_val = stats['weight']
    display_wt = f"{wt_val:.3f}" if (wt_val > 0 and wt_val < 0.1) else f"{wt_val:.1f}"
    print(f" {rank}. {area} ({stats['station_name']}): TỒN={stats['volume']} | T.LƯỢNG={display_wt} Tấn")
