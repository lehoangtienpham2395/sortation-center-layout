"""
sync_local_to_neon.py
──────────────────────────────────────────────────────────────────────────────
Công cụ đồng bộ 2 chiều / đẩy dữ liệu từ Local PostgreSQL (localhost:5433)
lên Neon Cloud PostgreSQL để GitHub Actions có thể tiếp tục chạy ngầm 24/7.
"""
import sys, os, psycopg2
from psycopg2.extras import execute_values

sys.stdout.reconfigure(encoding='utf-8')

LOCAL_PARAMS = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "postgres",
    "dbname": "postgres"
}
NEON_URL = "postgresql://neondb_owner:npg_i0dyTk6oeEmD@ep-dawn-poetry-atfofe2l-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def mirror_local_to_neon():
    print("🚀 1. Đọc dữ liệu từ Local PostgreSQL (localhost:5433)...")
    try:
        conn_local = psycopg2.connect(**LOCAL_PARAMS)
    except Exception as e:
        print(f"❌ Không thể kết nối Local PostgreSQL: {e}")
        return

    cur_local = conn_local.cursor()
    cur_local.execute("SELECT * FROM shipments WHERE is_active = 1")
    rows = cur_local.fetchall()
    col_names = [d[0] for d in cur_local.description]
    conn_local.close()
    print(f"   ℹ️ Đã lấy {len(rows):,} đơn active từ Local DB.")

    if not rows:
        print("   ⚠️ Không có đơn nào để đồng bộ.")
        return

    print("🚀 2. Đang kết nối & UPSERT lên Neon Cloud PostgreSQL...")
    conn_neon = psycopg2.connect(NEON_URL)
    cur_neon = conn_neon.cursor()

    # Tạo bảng nếu chưa tồn tại trên Neon
    cur_neon.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            waybillno           TEXT PRIMARY KEY,
            data_source         TEXT,
            weight              REAL,
            picknetworkname     TEXT,
            dispatch_plan       TEXT,
            pickup_time         TEXT,
            pickup_label        TEXT,
            pickup_ontime       TEXT,
            dispatchnetworktime TEXT,
            next_station        TEXT,
            tuyen               TEXT,
            rank                TEXT,
            inbound_network     TEXT,
            inbound_scandate    TEXT,
            outbound_scandate   TEXT,
            arrival_time        TEXT,
            dispatch_actual     TEXT,
            status_order        TEXT,
            time_ref            TEXT,
            is_backlog          INTEGER DEFAULT 0,
            is_active           INTEGER DEFAULT 1,
            last_updated        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn_neon.commit()

    # Xây dựng câu lệnh UPSERT
    cols_str = ", ".join(col_names)
    updates_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in col_names if col != 'waybillno'])
    
    upsert_query = f"""
        INSERT INTO shipments ({cols_str}) VALUES %s
        ON CONFLICT(waybillno) DO UPDATE SET {updates_str}, last_updated = NOW()
    """
    
    execute_values(cur_neon, upsert_query, rows, page_size=2000)
    conn_neon.commit()
    print(f"   ✅ Đã đồng bộ thành công {len(rows):,} bản ghi active lên Neon Cloud DB!")

    cur_neon.execute("SELECT count(*) FROM shipments WHERE weight = 0.0")
    zero_cnt = cur_neon.fetchone()[0]
    cur_neon.execute("SELECT AVG(weight) FROM shipments WHERE weight > 0")
    avg_wt = cur_neon.fetchone()[0]
    conn_neon.close()

    print(f"📊 Thống kê Neon Cloud DB hiện tại: Còn {zero_cnt:,} đơn weight=0 | Avg weight (>0): {avg_wt:.2f} kg")

if __name__ == "__main__":
    mirror_local_to_neon()
