import os
import sys
import psycopg2

def init_rebound_db():
    print("Running PostgreSQL Rebound & Data Freezing Migration...")
    pg_pass = os.environ.get('PGPASSWORD', 'Tien@giang0203')
    pg_db   = os.environ.get('PGDATABASE', 'logistics_db')
    pg_host = os.environ.get('PGHOST', '127.0.0.1')
    pg_port = int(os.environ.get('PGPORT', 5433))

    conn = psycopg2.connect(
        host=pg_host, port=pg_port, dbname=pg_db, user='postgres', password=pg_pass,
        connect_timeout=10
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Create raw schema and raw.scan_logs table
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw.scan_logs (
            id BIGSERIAL PRIMARY KEY,
            tracking TEXT NOT NULL,
            scan_type TEXT NOT NULL,
            scan_time TIMESTAMP NOT NULL,
            station TEXT,
            trip_code TEXT,
            cycle_no INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_scan_logs_tracking_time 
        ON raw.scan_logs(tracking, scan_time DESC);
    """)
    print("   [OK] Table raw.scan_logs and Composite Index ready")

    # 2. Add Rebound & Freezing columns to enriched.dispatch_enriched
    columns = [
        ("is_completed", "BOOLEAN DEFAULT FALSE"),
        ("cycle_no", "INT DEFAULT 1"),
        ("is_rebound", "INT DEFAULT 0"),
        ("return_count", "INT DEFAULT 0"),
        ("inbound_scandate_2", "TIMESTAMP"),
        ("operation_date_inbound_2", "DATE"),
        ("outbound_scandate_2", "TIMESTAMP")
    ]
    for col_name, col_type in columns:
        cur.execute(f"""
            ALTER TABLE enriched.dispatch_enriched 
            ADD COLUMN IF NOT EXISTS {col_name} {col_type};
        """)
    print("   [OK] Rebound columns added to enriched.dispatch_enriched")

    # 3. Create Trigger Function & Trigger for Data Protection & Rebound Lifecycle
    cur.execute("""
        CREATE OR REPLACE FUNCTION enriched.protect_completed_orders()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Nếu đã completed Lần 1 nhưng phát hiện Lượt Inbound 2 (Rebound quay đầu)
            IF OLD.is_completed = TRUE AND NEW.inbound_scandate_2 IS NOT NULL AND OLD.inbound_scandate_2 IS NULL THEN
                NEW.inbound_scandate := OLD.inbound_scandate; -- Bảo vệ mốc Lần 1
                NEW.created_time     := OLD.created_time;
                NEW.pickup_time      := OLD.pickup_time;
                NEW.is_completed     := FALSE; -- Mở lại trạng thái active cho Rebound
                NEW.is_active        := 1;
                NEW.is_backlog       := 1;
            ELSIF OLD.is_completed = TRUE AND NEW.outbound_scandate_2 IS NOT NULL THEN
                NEW.inbound_scandate := OLD.inbound_scandate;
                NEW.created_time     := OLD.created_time;
                NEW.is_completed     := TRUE; -- Đóng lại khi xuất kho Lần 2
                NEW.is_active        := 0;
                NEW.is_backlog       := 0;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    cur.execute("DROP TRIGGER IF EXISTS trg_protect_completed ON enriched.dispatch_enriched;")
    cur.execute("""
        CREATE TRIGGER trg_protect_completed
        BEFORE UPDATE ON enriched.dispatch_enriched
        FOR EACH ROW EXECUTE FUNCTION enriched.protect_completed_orders();
    """)
    print("   [OK] Trigger trg_protect_completed registered successfully")

    cur.close()
    conn.close()
    print("SUCCESS: PostgreSQL Rebound migration completed successfully!")

if __name__ == '__main__':
    init_rebound_db()
