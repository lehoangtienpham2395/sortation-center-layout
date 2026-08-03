import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

bn_hub_inbound = []
for d in data:
    st = str(d.get('pickup_station') or d.get('send_network') or d.get('Bưu cục nộp') or d.get('Bưu cục') or '').strip().upper()
    if 'BN HUB' in st or st.startswith(('HN ', 'HD ', 'HY ')):
        status = d.get('status') or d.get('Trạng thái')
        if status in ['Inbound', 'Đã nhập kho']:
            bn_hub_inbound.append(d)

print(f"Total BN HUB Inbound records found in inbound.json: {len(bn_hub_inbound)}")

trips_map = {}
fields_found = set()

for d in bn_hub_inbound:
    # Check all possible trip fields
    trip_id = (
        d.get('trip_code') or d.get('trip_id') or d.get('plate_number') or 
        d.get('vehicle_number') or d.get('Phiếu nhiệm vụ') or d.get('Mã chuyến xe') or
        d.get('pnv_code') or d.get('pnv') or d.get('linehaul_code') or d.get('shuttle_code')
    )
    t_str = str(trip_id).strip() if trip_id else 'NO_TRIP_ID'
    trips_map[t_str] = trips_map.get(t_str, 0) + int(d.get('volume') or 1)

print("\n=== Trip ID Breakdown for BN HUB Inbound Records ===")
for tid, count in trips_map.items():
    print(f"  Trip '{tid}': {count} orders")

print("\nSample BN HUB record keys:", list(bn_hub_inbound[0].keys()) if bn_hub_inbound else "None")
