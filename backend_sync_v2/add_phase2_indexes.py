"""
add_phase2_indexes.py — Migration: Backfill is_completed + Tao indexes Pool 1/Pool 2
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2

try:
    from sync_postgre import PG_DBNAME, PG_USER, PG_PASS, PG_HOST, PG_PORT
except ImportError:
    PG_DBNAME = 'logistics_db'; PG_USER = 'jfs_user'; PG_PASS = 'jfs_pass'
    PG_HOST = '127.0.0.1'; PG_PORT = 5433

conn = psycopg2.connect(dbname=PG_DBNAME, user=PG_USER, password=PG_PASS,
    host=PG_HOST, port=PG_PORT, connect_timeout=15,
    options='-c statement_timeout=120000')
cur = conn.cursor()
print("OK Connected:", PG_DBNAME)

# Buoc 1: Backfill is_completed theo 2 uu tien
print("\nBackfill is_completed...")
cur.execute("""
UPDATE enriched.dispatch_enriched
SET is_completed = TRUE, is_active = 0, is_backlog = 0
WHERE
    NOT (is_rebound = 1 AND outbound_scandate_2 IS NULL)
    AND (
        (created_time IS NOT NULL AND pickup_time IS NOT NULL
         AND (transporing_time IS NOT NULL OR arrival_scandate IS NOT NULL)
         AND inbound_scandate IS NOT NULL AND outbound_scandate IS NOT NULL)
        OR
        (inbound_scandate IS NOT NULL AND outbound_scandate IS NOT NULL
         AND outbound_scandate > inbound_scandate)
    )
    AND is_completed = FALSE;
""")
print(f"  Backfill: {cur.rowcount:,} rows -> is_completed=TRUE")
conn.commit()

# Verify
cur.execute("""SELECT is_active, is_completed, COUNT(*) FROM enriched.dispatch_enriched
    GROUP BY is_active, is_completed ORDER BY is_active, is_completed;""")
print("\n  Distribution:")
for r in cur.fetchall():
    print(f"    is_active={r[0]} is_completed={r[1]} count={r[2]:,}")

# Buoc 2: Tao indexes
print("\nTao indexes...")
idxs = [
    ("idx_enriched_active_completed",
     "CREATE INDEX IF NOT EXISTS idx_enriched_active_completed ON enriched.dispatch_enriched(is_active, is_completed);",
     "Composite (is_active, is_completed) Pool1"),
    ("idx_enriched_last_updated",
     "CREATE INDEX IF NOT EXISTS idx_enriched_last_updated ON enriched.dispatch_enriched(last_updated DESC);",
     "last_updated DESC Pool2"),
    ("idx_enriched_outbound_date",
     "CREATE INDEX IF NOT EXISTS idx_enriched_outbound_date ON enriched.dispatch_enriched(outbound_scandate DESC) WHERE outbound_scandate IS NOT NULL;",
     "outbound_scandate DESC Pool2"),
    ("idx_enriched_is_completed_partial",
     "CREATE INDEX IF NOT EXISTS idx_enriched_is_completed_partial ON enriched.dispatch_enriched(is_completed) WHERE is_completed = FALSE;",
     "Partial index is_completed=FALSE Pool1"),
]
for name, ddl, desc in idxs:
    try:
        cur.execute(ddl); conn.commit()
        print(f"  OK {name} — {desc}")
    except Exception as e:
        conn.rollback(); print(f"  WARN {name}: {e}")

# Buoc 3: Pool size
print("\nPool size estimate:")
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE is_active=1 OR is_completed=FALSE;")
p1 = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM enriched.dispatch_enriched
    WHERE is_active=1 OR is_completed=FALSE
       OR operation_date_inbound >= CURRENT_DATE-2
       OR operation_date_inbound_2 >= CURRENT_DATE-2
       OR outbound_scandate >= CURRENT_TIMESTAMP - INTERVAL '2 days'
       OR last_updated >= CURRENT_TIMESTAMP - INTERVAL '2 days';""")
p12 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched;")
tot = cur.fetchone()[0]
print(f"  Total: {tot:,} | Pool1: {p1:,} ({p1/tot*100:.1f}%) | Pool1+2: {p12:,} ({p12/tot*100:.1f}%)")
print(f"  Tiet kiem: {tot-p12:,} rows ({(tot-p12)/tot*100:.1f}% loai bo)")
conn.close()
print("\nDone!")
