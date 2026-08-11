import psycopg2, json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db', user='postgres',
    password='Tien@giang0203', host='127.0.0.1', port=5433
)
cur = conn.cursor()

SEP = "=" * 65

print(SEP)
print("  KIỂM TRA TRẠNG THÁI OUTBOUND TRONG DATABASE (PostgreSQL)")
print(SEP)

# 1. Thống kê theo ngày vận hành: Inbound chưa Outbound vs Đã Outbound
cur.execute("""
    SELECT
        operation_date_created,
        COUNT(*) AS total,
        COUNT(inbound_scandate) AS has_inbound,
        COUNT(outbound_scandate) AS has_outbound,
        COUNT(CASE WHEN inbound_scandate IS NOT NULL AND outbound_scandate IS NULL THEN 1 END) AS in_no_out,
        COUNT(CASE WHEN inbound_scandate IS NOT NULL AND outbound_scandate IS NOT NULL THEN 1 END) AS in_and_out
    FROM enriched.dispatch_enriched
    WHERE operation_date_created >= '2026-08-08'
    GROUP BY operation_date_created
    ORDER BY operation_date_created DESC
""")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()

print(f"{'NGÀY VẬN HÀNH':<15} {'TỔNG ĐƠN':>10} {'INBOUND':>10} {'OUTBOUND':>10} {'CHƯA OUTBOUND':>15} {'ĐÃ OUTBOUND':>15}")
print("-" * 78)
for r in rows:
    d = dict(zip(cols, r))
    dt_str = str(d['operation_date_created'])
    print(f"{dt_str:<15} {d['total']:>10,} {d['has_inbound']:>10,} {d['has_outbound']:>10,} {d['in_no_out']:>15,} {d['in_and_out']:>15,}")

print(SEP)
print("  XÁC NHẬN CHO 18.308 ĐƠN TRÊN LAYOUT:")
print(SEP)

# 2. Kiểm tra chi tiết 18.308 đơn trong inventory.json / backlog.json có outbound_time hay không
# Xem logic tạo inventory.json và backlog.json trong sync_postgre.py / pipeline_unified_v6.py
cur.execute("""
    SELECT
        COUNT(*) AS total_inventory_backlog,
        COUNT(outbound_scandate) AS count_with_outbound,
        COUNT(CASE WHEN outbound_scandate IS NULL THEN 1 END) AS count_without_outbound
    FROM enriched.dispatch_enriched
    WHERE inbound_scandate IS NOT NULL
      AND (outbound_scandate IS NULL OR operation_date_created >= '2026-08-10')
""")
r_check = cur.fetchone()
print(f"  - Số đơn đã Outbound  : {r_check[1]:,}")
print(f"  - Số đơn CHƯA Outbound : {r_check[2]:,}")

cur.close()
conn.close()
