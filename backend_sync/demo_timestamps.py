"""
DEMO: Trace mốc thời gian từng source trong PostgreSQL logistics_db
Chạy: python backend_sync/demo_timestamps.py
"""
import psycopg2
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db', user='postgres',
    password='Tien@giang0203', host='127.0.0.1', port=5433
)
cur = conn.cursor()

# ─── 1. Lấy mẫu đơn có đủ mốc thời gian ─────────────────────────────────────
cur.execute("""
    SELECT
        tracking,
        data_source,
        status_sys,
        pickup_station,
        is_completed,
        created_time,
        pickup_time,
        inbound_scandate,
        outbound_scandate,
        arrival_scandate,
        transporing_time,
        transported_time,
        operation_date_created,
        op_date_pickup,
        operation_date_inbound
    FROM enriched.dispatch_enriched
    WHERE
        created_time IS NOT NULL
        AND pickup_time IS NOT NULL
        AND inbound_scandate IS NOT NULL
        AND operation_date_created::text >= '2026-08-09'
    ORDER BY operation_date_created DESC, created_time DESC
    LIMIT 5
""")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()

SEP = "=" * 72
SEP2 = "-" * 72

print(SEP)
print("  DEMO: MỐC THỜI GIAN TỪNG ĐƠN THEO SOURCE (PostgreSQL logistics_db)")
print(SEP)

for row in rows:
    d = dict(zip(cols, row))
    print()
    print(f"  Tracking  : {d['tracking']}")
    print(f"  Source    : {d['data_source']}")
    print(f"  Station   : {d['pickup_station']}")
    print(f"  Status    : {d['status_sys']}  |  Completed: {d['is_completed']}")
    print(f"  {SEP2}")
    print(f"  [CREATED ]  created_time      = {d['created_time']}")
    print(f"  [PICKUP  ]  pickup_time       = {d['pickup_time']}")
    print(f"  [INBOUND ]  inbound_scandate  = {d['inbound_scandate']}")
    print(f"  [OUTBOUND]  outbound_scandate = {d['outbound_scandate']}")
    print(f"  [ARRIVAL ]  arrival_scandate  = {d['arrival_scandate']}")
    print(f"  [TRANSP. ]  transporing_time  = {d['transporing_time']}")
    print(f"  [TRANSD. ]  transported_time  = {d['transported_time']}")
    print(f"  --- OP DATE ---")
    print(f"  op_date_created   = {d['operation_date_created']}")
    print(f"  op_date_pickup    = {d['op_date_pickup']}")
    print(f"  op_date_inbound   = {d['operation_date_inbound']}")

print()
print(SEP)

# ─── 2. Thống kê theo SOURCE: nguồn nào lấy mốc gì ──────────────────────────
print("\n  THỐNG KÊ MỐC THỜI GIAN THEO TỪNG SOURCE (hôm nay)")
print(SEP)

cur.execute("""
    SELECT
        data_source,
        COUNT(*)                                         AS total,
        COUNT(created_time)                              AS has_created,
        COUNT(pickup_time)                               AS has_pickup,
        COUNT(inbound_scandate)                          AS has_inbound,
        COUNT(outbound_scandate)                         AS has_outbound,
        COUNT(arrival_scandate)                          AS has_arrival,
        COUNT(transporing_time)                          AS has_transporing,
        COUNT(transported_time)                          AS has_transported
    FROM enriched.dispatch_enriched
    WHERE operation_date_created::text >= '2026-08-10'
    GROUP BY data_source
    ORDER BY total DESC
""")
cols2 = [d[0] for d in cur.description]
rows2 = cur.fetchall()

print(f"  {'SOURCE':<30} {'TOTAL':>7} {'CREAT':>6} {'PICKUP':>7} {'INBND':>6} {'OUTBND':>7} {'ARRIV':>6} {'TRANSP':>7} {'TRAND':>6}")
print(f"  {SEP2}")
for row in rows2:
    d = dict(zip(cols2, row))
    src = str(d['data_source'])[:29]
    print(
        f"  {src:<30} {d['total']:>7,} "
        f"{d['has_created']:>6,} {d['has_pickup']:>7,} "
        f"{d['has_inbound']:>6,} {d['has_outbound']:>7,} "
        f"{d['has_arrival']:>6,} {d['has_transporing']:>7,} "
        f"{d['has_transported']:>6,}"
    )

print()
print(SEP)

# ─── 3. Xác nhận: created_time và pickup_time có bao giờ bằng nhau không? ───
print("\n  KIỂM TRA: created_time == pickup_time (ghi đè nhau)?")
print(SEP)
cur.execute("""
    SELECT COUNT(*) AS suspicious
    FROM enriched.dispatch_enriched
    WHERE
        created_time IS NOT NULL
        AND pickup_time IS NOT NULL
        AND ABS(EXTRACT(EPOCH FROM (created_time - pickup_time))) < 60
        AND operation_date_created::text >= '2026-08-01'
""")
suspicious = cur.fetchone()[0]
total_both_q = cur.execute("""
    SELECT COUNT(*) FROM enriched.dispatch_enriched
    WHERE created_time IS NOT NULL AND pickup_time IS NOT NULL
    AND operation_date_created::text >= '2026-08-01'
""")
total_both = cur.fetchone()[0]

print(f"  Đơn có cả created_time & pickup_time (từ 01/08) : {total_both:,}")
print(f"  Đơn có created_time ≈ pickup_time (±60 giây)    : {suspicious:,}")
if suspicious == 0:
    print("  ✅ KẾT LUẬN: KHÔNG CÓ GHI ĐÈ — 2 mốc hoàn toàn độc lập")
else:
    pct = suspicious / total_both * 100 if total_both else 0
    print(f"  ⚠️  CÓ {suspicious:,} đơn nghi ngờ ({pct:.1f}%) — cần kiểm tra thêm")

print(SEP)
cur.close()
conn.close()
