"""
migrate_to_local_pg.py — Migrate toàn bộ SQLite → Local PostgreSQL (Port 5433)
"""
import sqlite3
import os
import sys
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

LOCAL_PG_CONN = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "postgres",
    "dbname": "postgres"
}
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "db", "state.db")

# ── 1. Tạo bảng trên Local PG ──────────────────────────────────────
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS shipments (
    waybillNo           TEXT PRIMARY KEY,
    data_source         TEXT,
    weight              REAL,
    pickNetworkName     TEXT,
    dispatch_plan       TEXT,
    Pickup_time         TEXT,
    pickup_label        TEXT,
    Pickup_ontime       TEXT,
    dispatchNetworkTime TEXT,
    next_station        TEXT,
    tuyen               TEXT,
    rank                TEXT,
    inbound_network     TEXT,
    inbound_scanDate    TEXT,
    outbound_scanDate   TEXT,
    Arrival_time        TEXT,
    dispatch_actual     TEXT,
    status_order        TEXT,
    time_ref            TEXT,
    is_backlog          INTEGER DEFAULT 0,
    is_active           INTEGER DEFAULT 1,
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shipments_is_active    ON shipments(is_active);
CREATE INDEX IF NOT EXISTS idx_shipments_status       ON shipments(status_order);
CREATE INDEX IF NOT EXISTS idx_shipments_inbound_date ON shipments(inbound_scanDate);
CREATE INDEX IF NOT EXISTS idx_shipments_data_source  ON shipments(data_source);
"""

print("🔌 Kết nối Local PostgreSQL (Port 5433)...")
pg = psycopg2.connect(**LOCAL_PG_CONN)
pg.autocommit = False
cur = pg.cursor()

print("📋 Tạo bảng và index...")
cur.execute(CREATE_TABLE)
pg.commit()
print("✅ Schema PostgreSQL đã tạo thành công!")

# ── 2. Đọc data từ SQLite ──────────────────────────────────────────
print(f"\n📂 Đọc SQLite: {SQLITE_PATH}")
sq = sqlite3.connect(SQLITE_PATH)
sq.row_factory = sqlite3.Row

COLUMNS = [
    'waybillNo','data_source','weight','pickNetworkName','dispatch_plan',
    'Pickup_time','pickup_label','Pickup_ontime','dispatchNetworkTime',
    'next_station','Tuyến','Rank','inbound_network','inbound_scanDate',
    'outbound_scanDate','Arrival_time','dispatch_actual','status_order',
    'time_ref','is_backlog','is_active','last_updated'
]
PG_COLUMNS = [c.lower() if c in ('Tuyến','Rank') else c for c in COLUMNS]
# Map: SQLite 'Tuyến' → PG 'tuyen', 'Rank' → 'rank'
PG_COLUMNS[10] = 'tuyen'
PG_COLUMNS[11] = 'rank'

rows = sq.execute(f"SELECT {', '.join([f'\"{c}\"' for c in COLUMNS])} FROM shipments").fetchall()
sq.close()
print(f"📊 Tổng records trong SQLite: {len(rows):,}")

# ── 3. Migrate theo batch ──────────────────────────────────────────
BATCH_SIZE = 1000
cols_str = ', '.join(PG_COLUMNS)

UPSERT_SQL = f"""
    INSERT INTO shipments ({cols_str})
    VALUES %s
    ON CONFLICT (waybillNo) DO UPDATE SET
        data_source         = EXCLUDED.data_source,
        weight              = EXCLUDED.weight,
        pickNetworkName     = EXCLUDED.pickNetworkName,
        dispatch_plan       = EXCLUDED.dispatch_plan,
        Pickup_time         = EXCLUDED.Pickup_time,
        dispatchNetworkTime = EXCLUDED.dispatchNetworkTime,
        next_station        = EXCLUDED.next_station,
        inbound_scanDate    = EXCLUDED.inbound_scanDate,
        outbound_scanDate   = EXCLUDED.outbound_scanDate,
        status_order        = EXCLUDED.status_order,
        is_active           = EXCLUDED.is_active,
        last_updated        = NOW()
"""

print(f"\n🚀 Migrate {len(rows):,} records lên PostgreSQL (batch={BATCH_SIZE})...")
total = 0
for i in range(0, len(rows), BATCH_SIZE):
    batch = [tuple(r) for r in rows[i:i+BATCH_SIZE]]
    execute_values(cur, UPSERT_SQL, batch)
    pg.commit()
    total += len(batch)
    print(f"   📊 Đã migrate {total:,}/{len(rows):,} records...", flush=True)

print(f"\n✅ Migrate hoàn tất: {total:,} records lên Local PostgreSQL!")

# ── 4. Verify ──────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM shipments")
pg_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM shipments WHERE is_active = 1")
pg_active = cur.fetchone()[0]
print(f"\n📊 Local PG Verify:")
print(f"   Total records: {pg_count:,}")
print(f"   Active:        {pg_active:,}")

cur.close()
pg.close()
print("\n🎉 Hoàn thành di chuyển dữ liệu!")
