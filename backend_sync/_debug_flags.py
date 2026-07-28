import sys; sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn
conn = get_pg_conn(); cur = conn.cursor()

# Kiem tra kieu du lieu cua pickup_time
cur.execute("""
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema='enriched' AND table_name='dispatch_enriched'
  AND column_name IN ('pickup_time','arrival_scandate','inbound_scandate','outbound_scandate','created_time')
ORDER BY column_name
""")
print("=== COLUMN TYPES ===")
for r in cur.fetchall(): print(f"  {r[0]:<30} {r[1]:<30} {r[2]}")

# Xem 3 dong co pickup_time khong null
cur.execute("""
SELECT tracking, pickup_time, pickup_station2,
       arrival_scandate, inbound_scandate, outbound_scandate,
       flag_pickup, flag_arrival, flag_inbound
FROM enriched.dispatch_enriched
WHERE pickup_time IS NOT NULL
LIMIT 3
""")
print()
print("=== SAMPLE ROWS WITH pickup_time ===")
for r in cur.fetchall():
    print(f"  tracking={r[0]}")
    print(f"    pickup_time={r[1]}  arrival={r[3]}  inbound={r[4]}")
    print(f"    flag_pickup={r[6]}  flag_arrival={r[7]}  flag_inbound={r[8]}")

# Dem bao nhieu dong co pickup_time not null
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE pickup_time IS NOT NULL")
print()
print(f"Rows with pickup_time NOT NULL: {cur.fetchone()[0]:,}")

# Kiem tra: co the pickup_time la empty string?
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE pickup_time IS NOT NULL AND pickup_time::text != ''")
print(f"Rows with pickup_time non-empty: {cur.fetchone()[0]:,}")

conn.close()
