import psycopg2
import csv
import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"

# Load Master Layout mappings from valid.csv or inventory.json logic
OFFICIAL_LAYOUT_MAP = {
    'C24': ('BD BÌNH HÒA', '3'), 'C23': ('SG BẢY HIỀN', '3'), 'C12': ('SG PHÚ NHUẬN', '3'),
    'C21': ('AG THOẠI SƠN', '3'), 'C20': ('AG TỊNH BIÊN', '3'), 'C19': ('AG TÂN CHÂU', '3'),
    'C18': ('AG AN PHÚ', '3'), 'C17': ('VL CHỢ LÁCH', '3'), 'C16': ('SG NHƠN ĐỨC', '3'),
    'C15': ('ST PHÚ LỢI', '3'), 'C14': ('CT LONG MỸ', '3'), 'C13': ('ST VĨNH CHÂU', '3'),
    'B10': ('SG GÒ VẤP', '3'), 'C25': ('LA BẾN LỨC', '3'), 'C10': ('SG XUÂN HÒA', '3'),
    'C09': ('LA HẬU NGHĨA', '3'), 'C08': ('TG GÒ CÔNG', '3'), 'X': ('DT TN', '3'),
    'C06': ('BD DĨ AN', '3'), 'C05': ('SG KHÁNH HỘI', '3'), 'C04': ('SG BÌNH TRỊ ĐÔNG', '3'),
    'C03': ('SG BÌNH LỢI TRUNG', '3'), 'C02': ('SG HƯNG LONG', '3'), 'C01': ('SG CHỢ LỚN', '3'),
    'B15': ('SG TÂN NHỰT', '2'), 'B14': ('SG VĨNH LỘC', '2'), 'B13': ('VT XUYÊN MỘC', '2'),
    'B12': ('VT CHÂU ĐỨC', '2'), 'B11': ('SG AN PHÚ ĐÔNG', '2'), 'A03': ('SG TÂN THỚI HIỆP', '2'),
    'B09': ('SG TÂN TẠO', '2'), 'B08': ('SG CỦ CHI', '2'), 'B07': ('SG TÂN SƠN NHÌ', '2'),
    'B06': ('SG HIỆP BÌNH', '2'), 'B05': ('SG PHÚ LÂM', '2'), 'B04': ('SG AN LẠC', '2'),
    'B03': ('SG BÌNH TÂN', '2'), 'B02': ('SG TÂN HƯNG', '2'), 'B01': ('SG ĐÔNG HƯNG THUẬN', '2'),
    'A20': ('AG CẦN ĐĂNG', '1'), 'A19': ('AG LONG XUYÊN', '1'), 'A18': ('VT VŨNG TÀU', '1'),
    'A17': ('TG TRUNG AN', '1'), 'A15': ('LA TÂN AN', '1'), 'A14': ('TG AN HỮU', '1'),
    'A13': ('VL VĨNH LONG', '1'), 'A12': ('TG HÒA KHÁNH', '1'), 'A11': ('DT SA ĐÉC', '1'),
    'A10': ('DT CAO LÃNH', '1'), 'A09': ('CT NINH KIỀU', '1'), 'A08': ('CT BÌNH THỦY', '1'),
    'A07': ('CT Ô MÔN', '1'), 'A06': ('BN HUB', '1'), 'A04': ('LA ĐỨC HÒA', '3'),
    'A16': ('SG THỦ ĐỨC', '3'), 'A02': ('SG BÌNH LỢI', '3'), 'A01': ('SG HÓC MÔN', '3'),
    'C22': ('VT LONG ĐẤT', '3'), 'C26': ('SE TN', '3'), 'C11': ('LA CẦN ĐƯỚC', '3'),
    'B16': ('SG BÀ ĐIỂM', '2')
}

STATION_TO_AREA = {v[0].upper(): k for k, v in OFFICIAL_LAYOUT_MAP.items()}

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query all detailed active non-Outbound orders for Today (2026-08-01)
cur.execute('''
    SELECT 
        tracking as ma_don_hang,
        COALESCE(NULLIF(TRIM(pickup_station), ''), 'Chưa rõ') as buu_cuc_nop,
        COALESCE(NULLIF(TRIM(next_station), ''), NULLIF(TRIM(station_name), ''), 'Chưa rõ') as next_st_raw,
        dispatch_code,
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
    track, pk_st, next_raw, sc, st_sys, wt, op_d, cr_t, pk_t, arr_t, inb_t = r
    
    # Resolve mapped destination station and chute area_id
    next_upper = str(next_raw).strip().upper()
    is_north = (
        next_upper == 'BN HUB' or next_upper.startswith(('HN ', 'HD ', 'HY '))
    )
    
    if is_north:
        area_id = 'A06'
        dest_st = 'BN HUB'
    elif next_upper in STATION_TO_AREA:
        area_id = STATION_TO_AREA[next_upper]
        dest_st = OFFICIAL_LAYOUT_MAP[area_id][0]
    else:
        dest_st = next_raw if next_raw != 'Chưa rõ' else pk_st
        area_id = STATION_TO_AREA.get(dest_st.upper(), 'C01')
        if area_id in OFFICIAL_LAYOUT_MAP:
            dest_st = OFFICIAL_LAYOUT_MAP[area_id][0]

    formatted_rows.append({
        'tracking': track,
        'dest_station': dest_st,
        'area_id': area_id,
        'pickup_station': pk_st,
        'status': st_sys,
        'weight_ton': round(float(wt or 0), 4),
        'op_date': op_d,
        'cr_time': str(cr_t or ''),
        'pk_time': str(pk_t or ''),
        'arr_time': str(arr_t or ''),
        'inb_time': str(inb_t or '')
    })

top10_stations = {'BN HUB', 'SG THỦ ĐỨC', 'BD BÌNH HÒA', 'SG TÂN HƯNG', 'SG GÒ VẤP', 'DT TN', 'CT NINH KIỀU', 'SG CHỢ LỚN', 'SG CỦ CHI', 'BD DĨ AN'}

fp_all = os.path.join(ARTIFACT_DIR, 'danh_sach_tat_ca_10773_don_hang_volume_v2_01082026.csv')
fp_top10 = os.path.join(ARTIFACT_DIR, 'danh_sach_top10_chi_tiet_don_hang_v2_01082026.csv')

# Write ALL 10,773 orders CSV with correct Bưu Cục Đích & Mã Chute
with open(fp_all, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Mã Chute', 'Bưu Cục Đích (Next Station)', 'Bưu Cục Nộp', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(formatted_rows, 1):
        writer.writerow([i, r['tracking'], r['area_id'], r['dest_station'], r['pickup_station'], r['status'], r['weight_ton'], r['op_date'], r['cr_time'], r['pk_time'], r['arr_time'], r['inb_time']])

# Write Top 10 orders CSV
top10_rows = [r for r in formatted_rows if r['dest_station'].upper() in top10_stations]
with open(fp_top10, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Mã Chute', 'Bưu Cục Đích (Next Station)', 'Bưu Cục Nộp', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(top10_rows, 1):
        writer.writerow([i, r['tracking'], r['area_id'], r['dest_station'], r['pickup_station'], r['status'], r['weight_ton'], r['op_date'], r['cr_time'], r['pk_time'], r['arr_time'], r['inb_time']])

print(f"Exported ALL detailed orders CSV: {fp_all} ({len(formatted_rows)} rows)")
print(f"Exported Top 10 detailed orders CSV: {fp_top10} ({len(top10_rows)} rows)")
conn.close()
