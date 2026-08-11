import psycopg2, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db', user='postgres',
    password='Tien@giang0203', host='127.0.0.1', port=5433
)
cur = conn.cursor()

SEP = "=" * 65

# ─── 1. Đơn ngày 10/08 bị inbound rồi nhưng pickup_time vẫn NULL ──────────
print(SEP)
print("  DON INBOUND ma pickup_time = NULL (ngay 10/08)")
print("  => Day la don 'rot' van con bi dong bang")
print(SEP)
cur.execute("""
    SELECT
        tracking,
        created_time  AT TIME ZONE 'Asia/Ho_Chi_Minh' AS created_vn,
        pickup_time   AT TIME ZONE 'Asia/Ho_Chi_Minh' AS pickup_vn,
        inbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh' AS inbound_vn,
        status_sys,
        is_completed,
        last_updated  AT TIME ZONE 'Asia/Ho_Chi_Minh' AS last_upd
    FROM enriched.dispatch_enriched
    WHERE operation_date_created = '2026-08-10'
      AND pickup_time IS NULL
      AND inbound_scandate IS NOT NULL
    LIMIT 8
""")
rows = cur.fetchall()
cols  = [d[0] for d in cur.description]
for r in rows:
    d = dict(zip(cols, r))
    print(f"  {d['tracking']}  status={d['status_sys']}  completed={d['is_completed']}")
    print(f"    created  : {d['created_vn']}")
    print(f"    pickup   : {d['pickup_vn']}  <-- VAN NULL")
    print(f"    inbound  : {d['inbound_vn']}")
    print(f"    last_upd : {d['last_upd']}")
    print()

# ─── 2. Thống kê tổng ──────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created='2026-08-10'")
total_10 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created='2026-08-10' AND pickup_time IS NULL")
null_pk = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created='2026-08-10' AND inbound_scandate IS NOT NULL AND pickup_time IS NULL")
inb_no_pk = cur.fetchone()[0]

print(SEP)
print("  THONG KE NGAY 10/08")
print(SEP)
print(f"  Tong don               : {total_10:,}")
print(f"  pickup_time = NULL     : {null_pk:,}  ({null_pk/total_10*100:.1f}%)")
print(f"  Inbound ma khong pickup: {inb_no_pk:,}  <-- so don bi dong bang sai")

# ─── 3. Xem upsert ON CONFLICT logic trong DB ──────────────────────────────
print()
print(SEP)
print("  CHECK: is_completed flag bao ve du lieu khong bi ghi de?")
print(SEP)
cur.execute("""
    SELECT is_completed, COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE operation_date_created = '2026-08-10'
      AND pickup_time IS NULL
    GROUP BY is_completed ORDER BY is_completed
""")
for r in cur.fetchall():
    print(f"  is_completed={r[0]}  →  {r[1]:,} don pickup=NULL")

cur.close()
conn.close()
