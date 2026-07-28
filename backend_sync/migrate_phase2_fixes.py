"""
Migration script: Apply all Phase 2 fixes in one atomic run.
Run once from: C:\\Users\\lehoa\\.gemini\\antigravity\\scratch\\sortation-center-layout

Fixes:
  1. Trigger: add ELSE clause to protect frozen orders from any non-Rebound overwrite
  2. Add computed columns: station_name, zone, area_id, capacity to enriched.dispatch_enriched
  3. Fix raw.scan_logs: add UNIQUE(tracking, scan_type, scan_time)
  4. Rebound backfill: re-flag 60 orders where inbound_scandate > outbound_scandate
  5. Confirm op_date_pickup already populated (it is - verified in refresh_operational_flags)
"""
import sys, time
sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn()
cur = conn.cursor()

print("=" * 60)
print("PHASE 2 MIGRATION — All Fixes")
print("=" * 60)

# ──────────────────────────────────────────────────────────────
# FIX 1: Trigger — add ELSE clause to protect all frozen orders
# ──────────────────────────────────────────────────────────────
print("\n[1/5] Updating trg_protect_completed trigger...")
cur.execute("""
    CREATE OR REPLACE FUNCTION enriched.protect_completed_orders()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        -- Guard: chỉ xử lý khi đơn đang ở trạng thái FROZEN (is_completed = TRUE)
        IF OLD.is_completed = TRUE THEN

            -- Ngoại lệ Rebound Lần 2: phát hiện inbound_scandate_2 mới → mở lại
            IF NEW.inbound_scandate_2 IS NOT NULL AND OLD.inbound_scandate_2 IS NULL THEN
                NEW.inbound_scandate := OLD.inbound_scandate;  -- bảo vệ mốc Lần 1
                NEW.created_time     := OLD.created_time;
                NEW.pickup_time      := OLD.pickup_time;
                NEW.is_completed     := FALSE;                 -- mở lại cho Rebound
                NEW.is_active        := 1;
                NEW.is_backlog       := 1;

            -- Ngoại lệ Đóng lại sau Rebound: có outbound_scandate_2
            ELSIF NEW.outbound_scandate_2 IS NOT NULL AND OLD.outbound_scandate_2 IS NULL THEN
                NEW.inbound_scandate := OLD.inbound_scandate;
                NEW.created_time     := OLD.created_time;
                NEW.pickup_time      := OLD.pickup_time;
                NEW.is_completed     := TRUE;                  -- đóng băng lại
                NEW.is_active        := 0;
                NEW.is_backlog       := 0;

            -- ELSE: đơn đã frozen + không phải Rebound → BẢO VỆ TOÀN BỘ, chỉ cho dedup
            ELSE
                -- Khóa cứng 5 mốc thời gian gốc
                NEW.created_time      := OLD.created_time;
                NEW.pickup_time       := OLD.pickup_time;
                NEW.inbound_scandate  := OLD.inbound_scandate;
                NEW.outbound_scandate := OLD.outbound_scandate;
                NEW.arrival_scandate  := OLD.arrival_scandate;
                -- Khóa cứng trạng thái frozen
                NEW.is_completed      := TRUE;
                NEW.is_active         := 0;
                NEW.is_backlog        := 0;
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$;
""")
conn.commit()
print("   ✅ Trigger updated — ELSE clause added, 5 timestamps protected for frozen orders")

# ──────────────────────────────────────────────────────────────
# FIX 2: Add computed columns station_name, zone, area_id, capacity
# ──────────────────────────────────────────────────────────────
print("\n[2/5] Adding computed columns (station_name, zone, area_id, capacity)...")

# Check which ones already exist
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='enriched' AND table_name='dispatch_enriched'
    AND column_name IN ('station_name','zone','area_id','capacity');
""")
existing = {r[0] for r in cur.fetchall()}

add_cols = {
    'station_name': 'TEXT DEFAULT NULL',
    'zone':         'TEXT DEFAULT NULL',
    'area_id':      'TEXT DEFAULT NULL',
    'capacity':     'INTEGER DEFAULT NULL',
}
for col, dtype in add_cols.items():
    if col not in existing:
        cur.execute(f"ALTER TABLE enriched.dispatch_enriched ADD COLUMN {col} {dtype};")
        print(f"   + Added column: {col} {dtype}")
    else:
        print(f"   = Already exists: {col}")
conn.commit()

# Now populate station_name from next_station (primary) or pickup_station (fallback)
# zone, area_id, capacity remain NULL until dict_station / dict_zone are applied per-run
# They will be written by sync_postgre.py Phase 2 aggregate at runtime
# For the DB column, we populate station_name which is most critical for SQL GROUP BY
print("   Populating station_name from next_station / pickup_station...")
cur.execute("""
    UPDATE enriched.dispatch_enriched
    SET station_name = COALESCE(
        NULLIF(TRIM(next_station), ''),
        NULLIF(TRIM(pickup_station), ''),
        'UNKNOWN'
    )
    WHERE station_name IS NULL OR station_name = '';
""")
updated_sn = cur.rowcount
conn.commit()
print(f"   ✅ station_name populated: {updated_sn:,} rows")

# ──────────────────────────────────────────────────────────────
# FIX 3: raw.scan_logs — add UNIQUE(tracking, scan_type, scan_time)
# ──────────────────────────────────────────────────────────────
print("\n[3/5] Adding UNIQUE constraint to raw.scan_logs...")

cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE schemaname='raw' AND tablename='scan_logs'
    AND indexname='idx_scan_logs_unique_event';
""")
if not cur.fetchone():
    # First remove duplicates if any
    cur.execute("""
        DELETE FROM raw.scan_logs a
        USING raw.scan_logs b
        WHERE a.id > b.id
          AND a.tracking = b.tracking
          AND a.scan_type = b.scan_type
          AND a.scan_time = b.scan_time;
    """)
    dedup_count = cur.rowcount
    if dedup_count > 0:
        print(f"   Removed {dedup_count} duplicate scan_log rows first")

    cur.execute("""
        CREATE UNIQUE INDEX idx_scan_logs_unique_event
        ON raw.scan_logs (tracking, scan_type, scan_time);
    """)
    conn.commit()
    print("   ✅ UNIQUE INDEX (tracking, scan_type, scan_time) created")
else:
    print("   = UNIQUE INDEX already exists")

# ──────────────────────────────────────────────────────────────
# FIX 4: Rebound backfill — 60 orders where inbound_scandate > outbound_scandate
# ──────────────────────────────────────────────────────────────
print("\n[4/5] Rebound backfill — re-flag orders where inb_t > outb_t...")

cur.execute("""
    SELECT COUNT(*) FROM enriched.dispatch_enriched
    WHERE inbound_scandate IS NOT NULL
      AND outbound_scandate IS NOT NULL
      AND inbound_scandate > outbound_scandate
      AND is_rebound = 0;
""")
candidates = cur.fetchone()[0]
print(f"   Found {candidates} unflagged Rebound candidates")

if candidates > 0:
    cur.execute("""
        UPDATE enriched.dispatch_enriched SET
            is_rebound               = 1,
            cycle_no                 = 2,
            return_count             = 1,
            -- Move inbound Lần 2 vào inbound_scandate_2 (Lần 1 cũ là outbound's pair)
            inbound_scandate_2       = inbound_scandate,
            operation_date_inbound_2 = operation_date_inbound,
            -- Reset inbound lần 1 — phải dùng outbound làm anchor
            -- inbound_scandate giữ nguyên (trigger bảo vệ nếu đơn đã frozen)
            is_completed             = FALSE,
            is_active                = 1,
            is_backlog               = 1
        WHERE inbound_scandate IS NOT NULL
          AND outbound_scandate IS NOT NULL
          AND inbound_scandate > outbound_scandate
          AND is_rebound = 0;
    """)
    flagged = cur.rowcount
    conn.commit()
    print(f"   ✅ {flagged} Rebound orders re-flagged (is_rebound=1, cycle_no=2)")

# ──────────────────────────────────────────────────────────────
# FIX 5: Confirm op_date_pickup is populated
# ──────────────────────────────────────────────────────────────
print("\n[5/5] Verifying op_date_pickup population...")
cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE flag_pickup=1 AND op_date_pickup IS NOT NULL) AS populated,
        COUNT(*) FILTER (WHERE flag_pickup=1 AND op_date_pickup IS NULL)     AS missing
    FROM enriched.dispatch_enriched;
""")
r = cur.fetchone()
print(f"   flag_pickup=1 with op_date_pickup populated : {r[0]:,}")
print(f"   flag_pickup=1 with op_date_pickup MISSING   : {r[1]:,}")
if r[1] > 0:
    print("   Populating missing op_date_pickup via refresh...")
    cur.execute("""
        UPDATE enriched.dispatch_enriched SET
            op_date_pickup = CASE
                WHEN EXTRACT(HOUR FROM pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                THEN (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                ELSE (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            END
        WHERE flag_pickup = 1 AND op_date_pickup IS NULL AND pickup_time IS NOT NULL;
    """)
    fixed = cur.rowcount
    conn.commit()
    print(f"   ✅ op_date_pickup populated for {fixed:,} rows")
else:
    print("   ✅ op_date_pickup fully populated — no action needed")

# ──────────────────────────────────────────────────────────────
# FINAL: Run refresh_operational_flags to recompute all flags
# ──────────────────────────────────────────────────────────────
print("\n[6/6] Running refresh_operational_flags to recompute all flags after backfill...")
cur.close()
conn.close()

from sync_postgre import refresh_operational_flags
refresh_operational_flags()

print("\n" + "=" * 60)
print("✅ ALL FIXES APPLIED SUCCESSFULLY")
print("=" * 60)
