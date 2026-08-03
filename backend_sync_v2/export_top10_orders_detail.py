import psycopg2
import csv
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query all detailed active non-Outbound orders for Today (2026-08-01)
cur.execute('''
    SELECT 
        tracking as ma_don_hang,
        COALESCE(pickup_station, 'Chưa rõ') as buu_cuc_nop,
        COALESCE(station_name, 'Chưa rõ') as buu_cuc_dich,
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
    ORDER BY station_name, tracking;
''')

rows = cur.fetchall()
print(f"Total detailed non-outbound waybills found in DB for 01/08/2026: {len(rows):,} orders")

top10_stations = {'BN HUB', 'SG THỦ ĐỨC', 'BD BÌNH HÒA', 'SG TÂN HƯNG', 'SG GÒ VẤP', 'DT TN', 'CT NINH KIỀU', 'SG CHỢ LỚN', 'SG CỦ CHI', 'BD DĨ AN'}

fp_all = os.path.join(ARTIFACT_DIR, 'danh_sach_tat_ca_10773_don_hang_volume_01082026.csv')
fp_top10 = os.path.join(ARTIFACT_DIR, 'danh_sach_top10_chi_tiet_don_hang_01082026.csv')

# Write ALL 10,773 orders CSV
with open(fp_all, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Bưu Cục Đích (Chute)', 'Bưu Cục Nộp', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(rows, 1):
        writer.writerow([i, r[0], r[2], r[1], r[3], round(float(r[4] or 0), 4), r[5], str(r[6] or ''), str(r[7] or ''), str(r[8] or ''), str(r[9] or '')])

# Write Top 10 orders CSV
top10_rows = [r for r in rows if r[2].upper() in top10_stations or r[1].upper() in top10_stations or (r[2].upper() == 'BN HUB' or 'BN HUB' in r[2].upper())]
with open(fp_top10, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['STT', 'Mã Đơn Hàng (Tracking)', 'Bưu Cục Đích (Chute)', 'Bưu Cục Nộp', 'Trạng Thái', 'Trọng Lượng (Tấn)', 'Ngày Vận Hành', 'Thời Gian Tạo', 'Thời Gian Pickup', 'Thời Gian Đến HUB', 'Thời Gian Nhập Kho'])
    for i, r in enumerate(top10_rows, 1):
        writer.writerow([i, r[0], r[2], r[1], r[3], round(float(r[4] or 0), 4), r[5], str(r[6] or ''), str(r[7] or ''), str(r[8] or ''), str(r[9] or '')])

print(f"Exported ALL detailed orders CSV: {fp_all} ({len(rows)} rows)")
print(f"Exported Top 10 detailed orders CSV: {fp_top10} ({len(top10_rows)} rows)")
conn.close()
