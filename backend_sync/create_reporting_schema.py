import sys
sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn
conn = get_pg_conn()
cur = conn.cursor()

cur.execute('CREATE SCHEMA IF NOT EXISTS reporting;')
print('schema reporting: OK')

cur.execute("""
CREATE TABLE IF NOT EXISTS reporting.inbound_daily (
    id               SERIAL PRIMARY KEY,
    op_date          DATE          NOT NULL,
    station_name     VARCHAR(200),
    status           VARCHAR(50),
    volume           INT           DEFAULT 0,
    weight_ton       NUMERIC(10,4) DEFAULT 0,
    op_date_inbound  DATE,
    op_date_forecast DATE,
    op_date_pickup   DATE,
    op_date_arrival  DATE,
    inbound_hour     VARCHAR(5),
    drop_type        VARCHAR(30),
    trip_code        VARCHAR(100),
    is_rebound       SMALLINT      DEFAULT 0,
    return_count     INT           DEFAULT 0,
    record_type      VARCHAR(10)   DEFAULT 'rolling',
    refreshed_at     TIMESTAMPTZ   DEFAULT NOW()
)""")
cur.execute('CREATE INDEX IF NOT EXISTS idx_inb_daily_date    ON reporting.inbound_daily(op_date DESC)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_inb_daily_station ON reporting.inbound_daily(op_date, station_name)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_inb_daily_status  ON reporting.inbound_daily(op_date, status)')
print('inbound_daily: OK')

cur.execute("""
CREATE TABLE IF NOT EXISTS reporting.outbound_daily (
    id           SERIAL PRIMARY KEY,
    op_date      DATE          NOT NULL,
    zone         VARCHAR(10),
    area_id      VARCHAR(20),
    station_name VARCHAR(200),
    volume       INT           DEFAULT 0,
    weight_ton   NUMERIC(10,4) DEFAULT 0,
    capacity     INT           DEFAULT 780,
    record_type  VARCHAR(10)   DEFAULT 'rolling',
    refreshed_at TIMESTAMPTZ   DEFAULT NOW()
)""")
cur.execute('CREATE INDEX IF NOT EXISTS idx_out_daily_date    ON reporting.outbound_daily(op_date DESC)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_out_daily_station ON reporting.outbound_daily(op_date, station_name)')
print('outbound_daily: OK')

cur.execute("""
CREATE TABLE IF NOT EXISTS reporting.inventory_daily (
    id           SERIAL PRIMARY KEY,
    op_date      DATE          NOT NULL,
    zone         VARCHAR(10),
    area_id      VARCHAR(20),
    station_name VARCHAR(200),
    volume       INT           DEFAULT 0,
    weight_ton   NUMERIC(10,4) DEFAULT 0,
    capacity     INT           DEFAULT 780,
    record_type  VARCHAR(10)   DEFAULT 'rolling',
    refreshed_at TIMESTAMPTZ   DEFAULT NOW()
)""")
cur.execute('CREATE INDEX IF NOT EXISTS idx_inv_daily_date    ON reporting.inventory_daily(op_date DESC)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_inv_daily_station ON reporting.inventory_daily(op_date, station_name)')
print('inventory_daily: OK')

cur.execute("""
CREATE TABLE IF NOT EXISTS reporting.heatmap_daily (
    op_date      DATE        NOT NULL,
    hour_slot    VARCHAR(5)  NOT NULL,
    volume       INT         DEFAULT 0,
    record_type  VARCHAR(10) DEFAULT 'rolling',
    refreshed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (op_date, hour_slot)
)""")
cur.execute('CREATE INDEX IF NOT EXISTS idx_heatmap_date ON reporting.heatmap_daily(op_date DESC)')
print('heatmap_daily: OK')

cur.execute("""
CREATE TABLE IF NOT EXISTS reporting.kpi_daily (
    op_date             DATE PRIMARY KEY,
    total_inbound       INT           DEFAULT 0,
    total_outbound      INT           DEFAULT 0,
    total_pickup        INT           DEFAULT 0,
    total_created       INT           DEFAULT 0,
    total_rebound       INT           DEFAULT 0,
    rot_hom_truoc       INT           DEFAULT 0,
    rot_hom_nay         INT           DEFAULT 0,
    total_backlog       INT           DEFAULT 0,
    inbound_weight_ton  NUMERIC(10,4) DEFAULT 0,
    outbound_weight_ton NUMERIC(10,4) DEFAULT 0,
    outbound_rate       NUMERIC(6,2)  DEFAULT 0,
    record_type         VARCHAR(10)   DEFAULT 'rolling',
    snapped_at          TIMESTAMPTZ   DEFAULT NOW()
)""")
print('kpi_daily: OK')

conn.commit()

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='reporting' ORDER BY table_name")
rows = cur.fetchall()
print('\nTables in reporting schema:')
for r in rows:
    print('  reporting.' + r[0])

conn.close()
print('\nDONE!')
