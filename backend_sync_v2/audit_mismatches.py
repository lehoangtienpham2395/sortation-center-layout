import psycopg2
import csv
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load valid.csv
valid_csv_path = os.path.join(BASE_DIR, 'backend_sync', 'config', 'valid.csv')
dict_sortcode_to_area = {}
dict_station_to_area = {}
dict_area_to_station = {}

with open(valid_csv_path, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        st1 = r.get('Station_1', '').strip().upper()
        st2 = r.get('Station_2', '').strip().upper()
        sc = r.get('sortcode', '').strip().upper()
        area = r.get('area', '').strip().upper()
        
        if sc and area:
            dict_sortcode_to_area[sc] = area
        if st1 and area:
            dict_station_to_area[st1] = area
        if st2 and area:
            dict_station_to_area[st2] = area
        if area:
            dict_area_to_station[area] = r.get('Station_1', '').strip()

dict_station_to_area['3PL'] = 'C26'
dict_station_to_area['SE TN'] = 'C26'
dict_station_to_area['BN HUB'] = 'A06'
dict_area_to_station['C26'] = 'SE TN'
dict_area_to_station['A06'] = 'BN HUB'

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

cur.execute('''
    SELECT 
        tracking as ma_don_hang,
        COALESCE(NULLIF(TRIM(next_station), ''), NULLIF(TRIM(station_name), ''), 'Chưa rõ') as next_st_raw,
        COALESCE(NULLIF(TRIM(dispatch_code), ''), '') as sc_raw
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
      AND status_sys != 'Outbound';
''')

raw_rows = cur.fetchall()

v2_fallback_count = 0
affected_breakdown = {}

for r in raw_rows:
    track, next_raw, sc_raw = r
    next_upper = str(next_raw).strip().upper()
    sc_upper = str(sc_raw).strip().upper()
    
    is_north = (next_upper == 'BN HUB' or next_upper.startswith(('HN ', 'HD ', 'HY ')))
    
    if is_north:
        correct_area = 'A06'
        correct_st = 'BN HUB'
    elif sc_upper in dict_sortcode_to_area:
        correct_area = dict_sortcode_to_area[sc_upper]
        correct_st = dict_area_to_station.get(correct_area, next_raw)
    elif next_upper in dict_station_to_area:
        correct_area = dict_station_to_area[next_upper]
        correct_st = dict_area_to_station.get(correct_area, next_raw)
    else:
        correct_area = 'Chưa phân vùng'
        correct_st = next_raw

    # Simulate old v2 logic:
    if next_upper not in dict_station_to_area and not is_north and sc_upper not in dict_sortcode_to_area:
        v2_fallback_count += 1
        key = (next_raw, sc_raw, correct_area, correct_st)
        affected_breakdown[key] = affected_breakdown.get(key, 0) + 1

print(f"Audit completed across ALL {len(raw_rows):,} active Volume orders for 01/08/2026:")
print(f"Total orders affected by old v2/v3 fallback bug: {v2_fallback_count} orders")
print("\nBreakdown of affected orders and their TRUE destination chutes in v4:")
for (next_st, sc, c_area, c_st), cnt in sorted(affected_breakdown.items(), key=lambda x: x[1], reverse=True):
    print(f" - NextStation: '{next_st}' | Sortcode: '{sc}' -> TRUE CHUTE: {c_area} ({c_st}) [{cnt} orders]")

conn.close()
