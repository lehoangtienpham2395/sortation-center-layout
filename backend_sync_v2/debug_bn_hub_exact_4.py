import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

activeDate = '2026-08-01'

filteredInbound = []
for d in data:
    status = d.get('status') or d.get('Trạng thái') or ''
    inbOpDate = str(d.get('op_date_inbound') or d.get('Ngy vn hnh_Inbound') or '')[:10]
    if status in ['Inbound', 'Đã nhập kho'] and inbOpDate == activeDate:
        filteredInbound.append(d)

print(f"Total filteredInbound: {len(filteredInbound)}")

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

print("\n=== RESULTS ===")
for clean, item in fcMetrics.items():
    cnt_gte_10 = sum(1 for count in item['tripCounts'].values() if count >= 10)
    cnt_total_trips = len(item['tripCounts'])
    print(f"FC: '{item['fc']}' | total_orders={item['orders']} | total_trips={cnt_total_trips} | gte_10_trips={cnt_gte_10}")
    for tid, count in item['tripCounts'].items():
        print(f"   -> Trip '{tid}': {count} orders")
