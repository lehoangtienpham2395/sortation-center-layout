import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

activeDate = '2026-08-01'

filteredInbound = [
    d for d in data 
    if (d.get('status') == 'Inbound' or d.get('Trạng thái') == 'Inbound') 
    and str(d.get('op_date_inbound') or d.get('Ngy vn hnh_Inbound'))[:10] == activeDate
]

print(f"Total Inbound orders today ({activeDate}): {len(filteredInbound)}")

fcMetrics = {}

def getFC(name):
    if not name: return None
    clean = str(name).strip().upper()
    if not clean: return None
    if clean not in fcMetrics:
        fcMetrics[clean] = {'fc': str(name).strip(), 'tripCounts': {}, 'orders': 0, 'weight': 0.0}
    return fcMetrics[clean]

for d in filteredInbound:
    fcName = d.get('pickup_station') or d.get('send_network') or d.get('Bưu cục nộp') or d.get('Bưu cục gốc') or d.get('Bưu cục') or d.get('station_name') or 'Chưa rõ'
    fc = getFC(fcName)
    if fc:
        vol = int(d.get('volume') or d.get('Volume') or 1)
        wt = float(d.get('weight_ton') or d.get('Weight') or 0.0)
        fc['orders'] += vol
        fc['weight'] += wt
        tripId = d.get('trip_code') or d.get('trip_id') or d.get('plate_number') or d.get('vehicle_number') or d.get('Phiếu nhiệm vụ') or d.get('Mã chuyến xe')
        if tripId:
            tid = str(tripId).strip()
            fc['tripCounts'][tid] = fc['tripCounts'].get(tid, 0) + vol

print("\n=== All Sending FCs computed in Python ===")
for clean, item in fcMetrics.items():
    mainVehiclesCount = sum(1 for tid, cnt in item['tripCounts'].items() if cnt >= 10)
    if mainVehiclesCount == 0 and len(item['tripCounts']) > 0:
        mainVehiclesCount = 1
    print(f"Station: '{item['fc']}' -> Vehicles (cnt>=10): {mainVehiclesCount}, Total Orders: {item['orders']}, Weight: {item['weight']:.2f} Tấn, Unique Trips: {len(item['tripCounts'])}")
    print(f"   Trips Breakdown: {item['tripCounts']}\n")
