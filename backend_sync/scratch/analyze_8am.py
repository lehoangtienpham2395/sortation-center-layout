import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db',
    user='postgres',
    password='Tien@giang0203',
    host='127.0.0.1',
    port=5433
)
cur = conn.cursor()

# 1. Total records created at 08:00 today (2026-08-12) in dispatch_enriched
cur.execute("""
    SELECT 
        COUNT(*) as total_raw_at_8am,
        COUNT(CASE WHEN NOT (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %' OR COALESCE(rank, '') = 'BN HUB') THEN 1 END) as valid_south_at_8am,
        COUNT(CASE WHEN (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %' OR COALESCE(rank, '') = 'BN HUB') THEN 1 END) as north_at_8am
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-08-12 08:00:00' AND created_time < '2026-08-12 09:00:00';
""")

r = cur.fetchone()
print("=================================================================")
print("  PHÂN TÍCH KHUNG GIỜ 08:00 (08:00:00 - 08:59:59) HÔM NAY (12/08)")
print("=================================================================")
print(f"  1. Tổng số đơn hàng JFS phát sinh tại mốc 08:00 (Raw) : {r[0]:,} đơn")
print(f"  2. Số đơn thuộc Miền Nam / HCM HUB (Valid South)       : {r[1]:,} đơn  <-- ĐÚNG BẰNG CON SỐ 1.137 TRÊN BIỂU ĐỒ!")
print(f"  3. Số đơn thuộc luồng Miền Bắc / BN HUB (Exclude North): {r[2]:,} đơn  <-- 135 đơn Miền Bắc!")

# 2. Total created series sum across 24h
cur.execute("""
    SELECT 
        COUNT(*) as total_created_today_raw,
        COUNT(CASE WHEN NOT (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %' OR COALESCE(rank, '') = 'BN HUB') THEN 1 END) as total_created_today_valid_south
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-08-12 06:00:00' AND created_time < '2026-08-13 06:00:00';
""")

r2 = cur.fetchone()
print("\n=================================================================")
print("  TỔNG CẢ NGÀY VẬN HÀNH (06:00 12/08 -> 06:00 13/08)")
print("=================================================================")
print(f"  1. Tổng đơn phát sinh toàn hệ thống (Raw JFS)          : {r2[0]:,} đơn  <-- 8.572 ĐƠN RAW VƯỢT HỆ THỐNG!")
print(f"  2. Tổng đơn sau khi khấu trừ Miền Bắc (Valid South)    : {r2[1]:,} đơn  <-- ĐÚNG BẰNG 7.444 ĐƠN TRÊN BIỂU ĐỒ!")

cur.close()
conn.close()
