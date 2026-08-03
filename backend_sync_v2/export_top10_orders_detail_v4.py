import psycopg2
import csv
import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"

# Load official valid.csv mappings (Single source of truth)
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

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query all detailed active non-Outbound orders for Today (2026-08-01)
cur.execute('''
    SELECT 
        tracking as ma_don_hang,
        COALESCE(NULLIF(TRIM(next_station), ''), NULLIF(TRIM(station_name), ''), 'Chưa rõ') as next_st_raw,
        COALESCE(NULLIF(TRIM(dispatch_code), ''), '') as sc_raw,
        status_sys as trang_thai,
        COALESCE(orders_weight, 0)::numeric / 1000.0 as trong_luong_ton,
        COALESCE(op_date_pickup::date, operation_date_created::date)::text as ngay_van_hanh,
        created_time,
        pickup_time,
        arrival_scandate,
        inbound_scandate
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
      AND status_sys != 'Outbound'
    ORDER BY next_station, tracking;
''')

raw_rows = cur.fetchall()
print(f"Fetched {len(raw_rows):,} rows from PostgreSQL")

formatted_rows = []
for r in raw_rows:
    track, next_raw, sc_raw, st_sys, wt, op_d, cr_t, pk_t, arr_t, inb_t = r
    
    next_upper = str(next_raw).strip().upper()
    sc_upper = str(sc_raw).strip().upper()
    
    is_north = (next_upper == 'BN HUB' or next_upper.startswith(('HN ', 'HD ', 'HY ')))
    
    if is_north:
        area_id = 'A06'
        dest_st = 'BN HUB'
    elif sc_upper in dict_sortcode_to_area:
        area_id = dict_sortcode_to_area[sc_upper]
        dest_st = dict_area_to_station.get(area_id, next_raw)
    elif next_upper in dict_station_to_area:
        area_id = dict_station_to_area[next_upper]
        dest_st = dict_area_to_station.get(area_id, next_raw)
    else:
        dest_st = next_raw
        area_id = dict_station_to_area.get(dest_st.upper(), 'Chưa phân vùng')

    formatted_rows.append({
        'tracking': track,
        'dest_station': dest_st,
        'area_id': area_id,
        'status': st_sys,
        'weight_ton': round(float(wt or 0), 4),
        'op_date': op_d,
        'cr_time': str(cr_t or ''),
        'pk_time': str(pk_t or ''),
        'arr_time': str(arr_t or ''),
        'inb_time': str(inb_t or '')
    })

# Check the 10 target waybills mentioned by user
target_trackings = [
    '530005490107', '530020680107', '530021290107', '530023520108',
    '530028280107', '530036820107', '530040510108', '530051520108',
    '530054120108', '530060280107'
]

print("\n🎯 MAPPING CHECK FOR USER'S 10 WAYBILLS:")
for r in formatted_rows:
    if r['tracking'] in target_trackings:
        print(f"Tracking: {r['tracking']} -> Mã Chute: {r['area_id']} | Bưu Cục Đích: {r['dest_station']} | Status: {r['status']}")

top10_stations = {'BN HUB', 'SG THỦ ĐỨC', 'BD BÌNH HÒA', 'SG TÂN HƯNG', 'SG GÒ VẤP', 'DT TN', 'CT NINH KIỀU', 'SG CHỢ LỚN', 'SG CỦ CHI', 'BD DĨ AN'}

fp_all = os.path.join(ARTIFACT_DIR, 'danh_sach_tat_ca_10773_don_hang_volume_v4_01082026.csv')
fp_top10 = os.path.join(ARTIFACT_DIR, 'danh_sach_top10_chi_tiet_don_hang_v4_01082026.csv')

# Write ALL 10,773 orders CSV without Bưu Cục Nộp
with open(fp_all, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Mã Chute', 'Bưu Cục Đích (Next Station)', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(formatted_rows, 1):
        writer.writerow([i, r['tracking'], r['area_id'], r['dest_station'], r['status'], r['weight_ton'], r['op_date'], r['cr_time'], r['pk_time'], r['arr_time'], r['inb_time']])

# Write Top 10 orders CSV without Bưu Cục Nộp
top10_rows = [r for r in formatted_rows if r['dest_station'].upper() in top10_stations]
with open(fp_top10, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Mã Chute', 'Bưu Cục Đích (Next Station)', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(top10_rows, 1):
        writer.writerow([i, r['tracking'], r['area_id'], r['dest_station'], r['status'], r['weight_ton'], r['op_date'], r['cr_time'], r['pk_time'], r['arr_time'], r['inb_time']])

print(f"\nExported v4 ALL CSV: {fp_all} ({len(formatted_rows)} rows)")
print(f"Exported v4 Top 10 CSV: {fp_top10} ({len(top10_rows)} rows)")
conn.close()
