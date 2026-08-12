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
        COUNT(CASE WHEN NOT (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %') THEN 1 END) as south_and_outbound_north,
        COUNT(CASE WHEN (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %') THEN 1 END) as pickup_from_north
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-08-12 08:00:00' AND created_time < '2026-08-12 09:00:00';
""")

r = cur.fetchone()
print("=================================================================")
print("  PHÂN TÍCH KHUNG GIỜ 08:00 (08:00:00 - 08:59:59) THEO QUY TẮC MỚI")
print("=================================================================")
print(f"  1. Tổng số đơn JFS phát sinh mốc 08:00 (Raw)          : {r[0]:,} đơn")
print(f"  2. Số đơn Miền Nam + Hàng gửi đi Miền Bắc (KÈM BẮC GỬI ĐI): {r[1]:,} đơn  <-- ĐẦY ĐỦ VẬN HÀNH SAN SÀN!")
print(f"  3. Số đơn gửi TỪ Miền Bắc về (Pickup Bắc - Khấu trừ) : {r[2]:,} đơn")

cur.execute("""
    SELECT 
        COUNT(*) as total_created_today_raw,
        COUNT(CASE WHEN NOT (COALESCE(pickup_station, '') LIKE 'BN HUB%' OR COALESCE(pickup_station, '') LIKE 'HN %' OR COALESCE(pickup_station, '') LIKE 'HD %' OR COALESCE(pickup_station, '') LIKE 'HY %') THEN 1 END) as total_created_today_new_rule
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-08-12 06:00:00' AND created_time < '2026-08-13 06:00:00';
""")

r2 = cur.fetchone()
print("\n=================================================================")
print("  TỔNG CẢ NGÀY VẬN HÀNH THEO QUY TẮC MỚI")
print("=================================================================")
print(f"  1. Tổng đơn phát sinh toàn hệ thống (Raw JFS)          : {r2[0]:,} đơn")
print(f"  2. Tổng đơn theo Quy tắc mới (BẮC GỬI ĐI CỘNG VÀO)    : {r2[1]:,} đơn")

cur.close()
conn.close()
