"""
add_operational_flags.py
Migration: Them 7 cot vao enriched.dispatch_enriched
  - flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound (SMALLINT 0/1)
  - op_date_pickup DATE          (helper: tinh rot dong)
  - op_date_inbound_effective DATE (helper: fix rebound ngay nho 2)
"""
import sys, os
sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn()
conn.autocommit = False
cur = conn.cursor()

print("Step 1: ALTER TABLE - them 7 cot moi...")
migrations = [
    ("flag_created",             "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS flag_created              SMALLINT NOT NULL DEFAULT 1"),
    ("flag_pickup",              "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS flag_pickup               SMALLINT NOT NULL DEFAULT 0"),
    ("flag_arrival",             "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS flag_arrival              SMALLINT NOT NULL DEFAULT 0"),
    ("flag_inbound",             "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS flag_inbound              SMALLINT NOT NULL DEFAULT 0"),
    ("flag_outbound",            "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS flag_outbound             SMALLINT NOT NULL DEFAULT 0"),
    ("op_date_pickup",           "ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS op_date_pickup            DATE"),
    ("op_date_inbound_effective","ALTER TABLE enriched.dispatch_enriched ADD COLUMN IF NOT EXISTS op_date_inbound_effective DATE"),
]
for name, sql in migrations:
    cur.execute(sql)
    print(f"  + {name}")
conn.commit()

print()
print("Step 2: CREATE INDEX tren flag columns...")
indexes = [
    "CREATE INDEX IF NOT EXISTS idx_flag_inbound   ON enriched.dispatch_enriched(flag_inbound)  WHERE flag_inbound=1",
    "CREATE INDEX IF NOT EXISTS idx_flag_outbound  ON enriched.dispatch_enriched(flag_outbound) WHERE flag_outbound=1",
    "CREATE INDEX IF NOT EXISTS idx_flag_pickup    ON enriched.dispatch_enriched(flag_pickup)   WHERE flag_pickup=1",
    "CREATE INDEX IF NOT EXISTS idx_op_date_pickup ON enriched.dispatch_enriched(op_date_pickup)",
    "CREATE INDEX IF NOT EXISTS idx_op_date_inb_eff ON enriched.dispatch_enriched(op_date_inbound_effective)",
]
for sql in indexes:
    cur.execute(sql)
    name = sql.split('idx_')[1].split(' ')[0]
    print(f"  + idx_{name}")
conn.commit()

print()
print("Step 3: BACKFILL 7 cot - atomic update toan bo 78K rows...")
# Single atomic UPDATE - tinh lai tat ca 7 cot cung luc
cur.execute("""
UPDATE enriched.dispatch_enriched SET
    flag_created   = 1,
    flag_pickup    = CASE WHEN pickup_time IS NOT NULL THEN 1 ELSE 0 END,
    flag_arrival   = CASE WHEN arrival_scandate IS NOT NULL THEN 1 ELSE 0 END,
    flag_inbound   = CASE
                        WHEN inbound_scandate IS NOT NULL THEN 1
                        WHEN is_rebound = 1 AND inbound_scandate_2 IS NOT NULL THEN 1
                        ELSE 0
                     END,
    flag_outbound  = CASE
                        WHEN outbound_scandate IS NOT NULL THEN 1
                        WHEN is_rebound = 1 AND outbound_scandate_2 IS NOT NULL THEN 1
                        ELSE 0
                     END,
    op_date_pickup = CASE
                        WHEN pickup_time IS NULL THEN NULL
                        WHEN EXTRACT(HOUR FROM pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                        THEN (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                        ELSE (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                     END,
    op_date_inbound_effective = CASE
                        WHEN is_rebound = 1 AND operation_date_inbound_2 IS NOT NULL
                        THEN operation_date_inbound_2
                        ELSE operation_date_inbound
                     END
""")
updated = cur.rowcount
conn.commit()
print(f"  Updated: {updated:,} rows")

print()
print("Step 4: Verify kết quả...")
cur.execute("""
SELECT
    SUM(flag_created)   AS total_created,
    SUM(flag_pickup)    AS total_pickup,
    SUM(flag_arrival)   AS total_arrival,
    SUM(flag_inbound)   AS total_inbound,
    SUM(flag_outbound)  AS total_outbound,
    SUM(CASE WHEN flag_inbound=1 AND flag_outbound=0 THEN 1 ELSE 0 END) AS total_backlog,
    COUNT(op_date_pickup) AS has_op_date_pickup,
    COUNT(op_date_inbound_effective) AS has_op_date_inb_eff
FROM enriched.dispatch_enriched
""")
r = cur.fetchone()
cols = ['created','pickup','arrival','inbound','outbound','backlog','op_dt_pickup','op_dt_inb_eff']
for c, v in zip(cols, r):
    print(f"  flag_{c:<20}: {v:>8,}")

print()
print("Step 5: Sample - 5 don Rớt (pickup=1, inbound=0, arrival=0)...")
cur.execute("""
SELECT tracking, op_date_pickup, operation_date_created,
       flag_pickup, flag_arrival, flag_inbound, flag_outbound
FROM enriched.dispatch_enriched
WHERE flag_pickup=1 AND flag_inbound=0 AND flag_arrival=0 AND is_rebound=0
LIMIT 5
""")
rows = cur.fetchall()
if rows:
    print(f"  {'tracking':<20} {'op_dt_pickup':<14} {'op_dt_created':<14} {'pk':>3} {'arr':>4} {'inb':>4} {'out':>4}")
    for row in rows:
        print(f"  {str(row[0]):<20} {str(row[1]):<14} {str(row[2]):<14} {row[3]:>3} {row[4]:>4} {row[5]:>4} {row[6]:>4}")
else:
    print("  (Khong co don rot hien tai)")

conn.close()
print()
print("MIGRATION DONE!")
