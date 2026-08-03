import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('public/data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

activeDate = '2026-08-01'

def normalizeDateStr(d):
    if not d: return ''
    return str(d)[:10]

def isDateMatch(rDate, aDate):
    normR = normalizeDateStr(rDate)
    normA = normalizeDateStr(aDate)
    return normR == normA

def getRowOpDate(d):
    return d.get('Ngày vận hành') or d.get('op_date') or d.get('op_date_forecast') or d.get('Ngày vận hành_Forecast') or d.get('op_date_inbound') or ''

def getWaterfallStatus(d):
    return d.get('status') or d.get('Trạng thái') or ''

filteredInbound = [
    d for d in data 
    if getWaterfallStatus(d) == 'Inbound' and isDateMatch(getRowOpDate(d), activeDate)
]

print(f"filteredInbound total count: {len(filteredInbound)}")

fcMetrics = {}
for d in filteredInbound:
    fcName = d.get('pickup_station') or d.get('send_network') or d.get('Bưu cục nộp') or d.get('Bưu cục gốc') or d.get('Bưu cục') or d.get('station_name') or 'Chưa rõ'
    clean = str(fcName).strip().upper()
    if clean not in fcMetrics:
        fcMetrics[clean] = {'fc': str(fcName).strip(), 'tripCounts': {}, 'orders': 0, 'weight': 0.0}
    
    vol = int(d.get('volume') or d.get('Volume') or 1)
    wt = float(d.get('weight_ton') or d.get('Weight') or 0.0)
    fcMetrics[clean]['orders'] += vol
    fcMetrics[clean]['weight'] += wt
    
    tripId = d.get('trip_code') or d.get('trip_id') or d.get('plate_number') or d.get('vehicle_number') or d.get('Phiếu nhiệm vụ') or d.get('Mã chuyến xe')
    if tripId:
        tid = str(tripId).strip()
        fcMetrics[clean]['tripCounts'][tid] = fcMetrics[clean]['tripCounts'].get(tid, 0) + vol

print("\n=== JS-EXACT FC METRICS ===")
for clean, item in fcMetrics.items():
    main_cnt = 0
    for tid, count in item['tripCounts'].items():
        if count >= 10:
            main_cnt += 1
    if main_cnt == 0 and len(item['tripCounts']) > 0:
        main_cnt = 1
    print(f"Station: '{item['fc']}' -> vehicles={main_cnt}, orders={item['orders']}, total_trips={len(item['tripCounts'])}")
    for tid, count in item['tripCounts'].items():
        print(f"   -> Trip '{tid}': {count} orders (>= 10? {count >= 10})")
