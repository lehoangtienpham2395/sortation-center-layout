import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def isNorthRow(row):
    if not row: return False
    if isinstance(row, str):
        clean = row.strip().upper()
        return clean == 'BN HUB' or clean.startswith(('HN ', 'HD ', 'HY '))
    if row.get('is_north') is True or str(row.get('region')).lower() == 'north':
        return True
    st = str(row.get('station_name') or row.get('pickup_station') or row.get('send_network') or row.get('Bưu cục') or '').strip().upper()
    return st == 'BN HUB' or st.startswith(('HN ', 'HD ', 'HY '))

activeDate = '2026-08-01'

filteredInbound = [
    d for d in data 
    if (d.get('status') == 'Inbound' or d.get('Trạng thái') == 'Inbound') 
    and str(d.get('op_date_inbound') or d.get('Ngy vn hnh_Inbound') or '')[:10] == activeDate
]

fcMetrics = {}
def getFC(name):
    if not name: return None
    clean = str(name).strip().upper()
    if not clean: return None
    if clean not in fcMetrics:
        fcMetrics[clean] = {'fc': str(name).strip(), 'tripCounts': {}, 'orders': 0, 'weight': 0.0}
    return fcMetrics[clean]

for d in filteredInbound:
    rawFcName = d.get('pickup_station') or d.get('send_network') or d.get('Bưu cục nộp') or d.get('Bưu cục gốc') or d.get('Bưu cục') or d.get('station_name') or 'Chưa rõ'
    if isNorthRow(d):
        rawFcName = 'BN HUB'
    
    fc = getFC(rawFcName)
    if fc:
        vol = int(d.get('volume') or d.get('Volume') or 1)
        wt = float(d.get('weight_ton') or d.get('Weight') or 0.0)
        fc['orders'] += vol
        fc['weight'] += wt
        tripId = d.get('trip_code') or d.get('trip_id') or d.get('plate_number') or d.get('vehicle_number') or d.get('Phiếu nhiệm vụ') or d.get('Mã chuyến xe')
        if tripId:
            tid = str(tripId).strip()
            fc['tripCounts'][tid] = fc['tripCounts'].get(tid, 0) + vol

print("\n=== NORTHERN STATIONS MERGED INTO 'BN HUB' ===")
for clean, item in fcMetrics.items():
    main_cnt = sum(1 for count in item['tripCounts'].values() if count >= 10)
    if main_cnt == 0 and len(item['tripCounts']) > 0:
        main_cnt = 1
    print(f"Station: '{item['fc']}' -> vehicles={main_cnt}, orders={item['orders']}, weight={item['weight']:.2f} Tấn")
    print(f"   Trips breakdown: {item['tripCounts']}")
