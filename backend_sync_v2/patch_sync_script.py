"""
patch_sync_script.py — Script programmatically patches sync_to_sheets.py to migrate from SQLite to PostgreSQL
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')

SYNC_SCRIPT_PATH = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync\sync_to_sheets.py"

with open(SYNC_SCRIPT_PATH, "r", encoding="utf-8") as f:
    content = f.read()

replacements = []

# ── 1. Replace Import ──────────────────────────────────────────────
old_import = "import sqlite3"
new_import = """import psycopg2
from psycopg2.extras import execute_values"""
replacements.append((old_import, new_import, "Import psycopg2"))

# ── 2. Replace DB_FILE with Connection Params ──────────────────────
old_db_file = 'DB_FILE      = os.path.join(BASE_DIR, "db", "state.db")'
new_db_file = """DB_CONN_PARAMS = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "postgres",
    "dbname": "postgres"
}

DB_KEYS_MAP = {
    'waybillno': 'waybillNo',
    'data_source': 'data_source',
    'weight': 'weight',
    'picknetworkname': 'pickNetworkName',
    'dispatch_plan': 'dispatch_plan',
    'pickup_time': 'Pickup_time',
    'pickup_label': 'pickup_label',
    'pickup_ontime': 'Pickup_ontime',
    'dispatchnetworktime': 'dispatchNetworkTime',
    'next_station': 'next_station',
    'tuyen': 'Tuyến',
    'rank': 'Rank',
    'inbound_network': 'inbound_network',
    'inbound_scandate': 'inbound_scanDate',
    'outbound_scandate': 'outbound_scanDate',
    'arrival_time': 'Arrival_time',
    'dispatch_actual': 'dispatch_actual',
    'status_order': 'status_order',
    'time_ref': 'time_ref',
    'is_backlog': 'is_backlog',
    'is_active': 'is_active',
    'last_updated': 'last_updated'
}

def pg_row_to_dict(col_names, row):
    d = {}
    for col, val in zip(col_names, row):
        key = DB_KEYS_MAP.get(col.lower(), col)
        if val is None and key not in ('weight', 'is_backlog', 'is_active', 'last_updated'):
            d[key] = ""
        else:
            d[key] = val
    return d
"""
replacements.append((old_db_file, new_db_file, "DB_CONN_PARAMS"))

# ── 3. Replace init_db ─────────────────────────────────────────────
old_init_db = """def init_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # ⚡ TỐI ƯU HÓA HIỆU NĂNG GHI/ĐỌC SQLITE CỰC ĐẠI
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = OFF")
    c.execute("PRAGMA cache_size = -64000")  # Cache RAM 64MB
    c.execute("PRAGMA temp_store = MEMORY")
    c.execute("PRAGMA count_changes = OFF")
    
    # 1. Tạo bảng shipments mới
    c.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS shipments (
            waybillNo TEXT PRIMARY KEY,
            data_source TEXT,
            weight REAL,
            pickNetworkName TEXT,
            dispatch_plan TEXT,
            Pickup_time TEXT,
            pickup_label TEXT,
            Pickup_ontime TEXT,
            dispatchNetworkTime TEXT,
            next_station TEXT,
            Tuyến TEXT,
            Rank TEXT,
            inbound_network TEXT,
            inbound_scanDate TEXT,
            outbound_scanDate TEXT,
            Arrival_time TEXT,
            dispatch_actual TEXT,
            status_order TEXT,
            time_ref TEXT,
            is_backlog INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    \"\"\")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_time_ref ON shipments(time_ref)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_status ON shipments(status_order)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_active ON shipments(is_active)")
    
    # 2. Kiểm tra nếu bảng inventory cũ tồn tại thì migrate sang shipments
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory'")
    if c.fetchone():
        print("   📦 Phát hiện bảng 'inventory' cũ. Bắt đầu migrate sang bảng 'shipments'...")
        try:
            # Kiểm tra xem cột Arrival_time có tồn tại trong inventory không, tự động thêm nếu chưa có
            try:
                c.execute("ALTER TABLE inventory ADD COLUMN Arrival_time TEXT")
            except Exception:
                pass
                
            c.execute(\"\"\"
                INSERT OR IGNORE INTO shipments (
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    is_backlog, is_active, last_updated
                )
                SELECT 
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    CASE WHEN inbound_scanDate = 'Backlog' THEN 1 ELSE 0 END,
                    CASE WHEN (inbound_scanDate IS NULL OR inbound_scanDate = '' OR inbound_scanDate = 'Backlog') 
                          AND (outbound_scanDate IS NULL OR outbound_scanDate = '') THEN 1 ELSE 0 END,
                    last_updated
                FROM inventory
            \"\"\")
            conn.commit()
            print("   ✅ Migrate dữ liệu thành công!")
            # Drop bảng cũ
            c.execute("DROP TABLE inventory")
            conn.commit()
            print("   🗑️ Đã xóa bảng 'inventory' cũ.")
        except Exception as e_migrate:
            print(f"   ⚠️ Lỗi migrate dữ liệu: {e_migrate}")
            
    # Tự động dọn dẹp các bản ghi ĐÃ RỜI HUB / Inbound (không active) cũ hơn 7 ngày để tối ưu hóa DB
    try:
        limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(\"\"\"
            DELETE FROM shipments 
            WHERE is_active = 0 
              AND datetime(last_updated) < datetime(?)
        \"\"\", (limit_date,))
        conn.commit()
    except Exception as e_clean:
        print(f"   ⚠️ Lỗi dọn dẹp database: {e_clean}")
        
    conn.close()"""

new_init_db = """def init_db():
    conn = psycopg2.connect(**DB_CONN_PARAMS)
    c = conn.cursor()
    
    # 1. Tạo bảng shipments mới
    c.execute(\"\"\"
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
    \"\"\")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_time_ref ON shipments(time_ref)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_status ON shipments(status_order)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_active ON shipments(is_active)")
    conn.commit()
    
    # Tự động dọn dẹp các bản ghi ĐÃ RỜI HUB / Inbound (không active) cũ hơn 7 ngày để tối ưu hóa DB
    try:
        c.execute(\"\"\"
            DELETE FROM shipments 
            WHERE is_active = 0 
              AND last_updated < NOW() - INTERVAL '7 days'
        \"\"\")
        conn.commit()
    except Exception as e_clean:
        print(f"   ⚠️ Lỗi dọn dẹp database: {e_clean}")
        
    conn.close()"""
replacements.append((old_init_db, new_init_db, "init_db"))

# ── 4. Replace Inbound aggregated query ───────────────────────────
old_inbound_query = """    try:
        conn = sqlite3.connect(DB_FILE)
        df_ship = pd.read_sql_query(\"\"\"
            SELECT pickNetworkName, status_order, weight, 
                   inbound_scanDate, dispatchNetworkTime, Pickup_time, Arrival_time
            FROM shipments
        \"\"\", conn)
        conn.close()
    except Exception as e_db:"""

new_inbound_query = """    try:
        conn = psycopg2.connect(**DB_CONN_PARAMS)
        df_ship = pd.read_sql_query(\"\"\"
            SELECT picknetworkname AS "pickNetworkName", status_order, weight, 
                   inbound_scandate AS "inbound_scanDate", dispatchnetworktime AS "dispatchNetworkTime", 
                   pickup_time AS "Pickup_time", arrival_time AS "Arrival_time"
            FROM shipments
        \"\"\", conn)
        conn.close()
    except Exception as e_db:"""
replacements.append((old_inbound_query, new_inbound_query, "Inbound aggregated query"))

# ── 5. Replace Arrival sheet query ────────────────────────────────
old_arrival_query = """    try:
        conn = sqlite3.connect(DB_FILE)
        df_arr_raw = pd.read_sql_query(\"\"\"
            SELECT waybillNo, pickNetworkName AS Pickup_station, Arrival_time, inbound_scanDate
            FROM shipments
            WHERE Arrival_time IS NOT NULL AND Arrival_time != ''
        \"\"\", conn)
        conn.close()
    except Exception as e_arr_db:"""

new_arrival_query = """    try:
        conn = psycopg2.connect(**DB_CONN_PARAMS)
        df_arr_raw = pd.read_sql_query(\"\"\"
            SELECT waybillno AS "waybillNo", picknetworkname AS "Pickup_station", arrival_time AS "Arrival_time", inbound_scandate AS "inbound_scanDate"
            FROM shipments
            WHERE arrival_time IS NOT NULL AND arrival_time != ''
        \"\"\", conn)
        conn.close()
    except Exception as e_arr_db:"""
replacements.append((old_arrival_query, new_arrival_query, "Arrival query"))

# ── 6. Replace run_backlog_inv query ─────────────────────────────
old_backlog_inv_query = """        try:
            conn = sqlite3.connect(DB_FILE)
            # ✅ Chỉ đọc đơn đang active (is_active=1) và chưa rời HUB
            df_db_inv = pd.read_sql_query(
                \"\"\"SELECT next_station, status_order, weight, waybillNo, time_ref
                   FROM shipments
                   WHERE is_active = 1
                     AND status_order != 'Đã rời HUB'\"\"\",
                conn
            )
            conn.close()"""

new_backlog_inv_query = """        try:
            conn = psycopg2.connect(**DB_CONN_PARAMS)
            # ✅ Chỉ đọc đơn đang active (is_active=1) và chưa rời HUB
            df_db_inv = pd.read_sql_query(
                \"\"\"SELECT next_station, status_order, weight, waybillno AS "waybillNo", time_ref
                   FROM shipments
                   WHERE is_active = 1
                     AND status_order != 'Đã rời HUB'\"\"\",
                conn
            )
            conn.close()"""
replacements.append((old_backlog_inv_query, new_backlog_inv_query, "run_backlog_inv query"))

# ── 7. Replace reconcile_outbound_5days updates ──────────────────
old_reconcile = """    # Cập nhật ngược vào DB: đánh dấu Đã rời HUB
    try:
        conn    = sqlite3.connect(DB_FILE)
        c       = conn.cursor()
        updated = 0
        for wb, info in outbound_map.items():
            c.execute(\"\"\"
                UPDATE shipments
                SET outbound_scanDate = ?,
                    status_order      = 'Đã rời HUB',
                    is_active         = 0,
                    last_updated      = CURRENT_TIMESTAMP
                WHERE waybillNo = ?
                  AND is_active = 1
                  AND (outbound_scanDate = '' OR outbound_scanDate IS NULL
                       OR outbound_scanDate < ?)
            \"\"\", (info['time'], wb, info['time']))
            updated += c.rowcount
        conn.commit()
        conn.close()
        print(f"   ✅ [Reconcile Outbound] Cập nhật {updated:,} đơn → 'Đã rời HUB'.")
    except Exception as e:"""

new_reconcile = """    # Cập nhật ngược vào DB: đánh dấu Đã rời HUB
    try:
        conn    = psycopg2.connect(**DB_CONN_PARAMS)
        c       = conn.cursor()
        updated = 0
        for wb, info in outbound_map.items():
            c.execute(\"\"\"
                UPDATE shipments
                SET outbound_scandate = %s,
                    status_order      = 'Đã rời HUB',
                    is_active         = 0,
                    last_updated      = NOW()
                WHERE waybillno = %s
                  AND is_active = 1
                  AND (outbound_scandate = '' OR outbound_scandate IS NULL
                       OR outbound_scandate < %s)
            \"\"\", (info['time'], wb, info['time']))
            updated += c.rowcount
        conn.commit()
        conn.close()
        print(f"   ✅ [Reconcile Outbound] Cập nhật {updated:,} đơn → 'Đã rời HUB'.")
    except Exception as e:"""
replacements.append((old_reconcile, new_reconcile, "reconcile_outbound_5days update"))

# ── 8. Replace run_once loading & cleanup ────────────────────────
old_load_once = """    # Load active records from SQLite
    db_records = {}
    init_db()
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Tự động dọn dẹp các đơn kẹt quá 3 ngày không có log xuất kho
        # 1. Đối với các đơn đã quét Inbound
        c.execute(\"\"\"
            UPDATE shipments 
            SET status_order = 'Đã rời HUB', is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate != '' AND inbound_scanDate IS NOT NULL)
              AND datetime(inbound_scanDate) < datetime('now', '+7 hours', '-3 days')
        \"\"\")
        cnt1 = c.rowcount
        
        # 2. Đối với các đơn mới chỉ ở trạng thái Forecast/Pickup (chưa có inbound scan)
        c.execute(\"\"\"
            UPDATE shipments 
            SET is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
              AND (
                (Pickup_time != '' AND Pickup_time IS NOT NULL AND datetime(Pickup_time) < datetime('now', '+7 hours', '-3 days'))
                OR
                ((Pickup_time = '' OR Pickup_time IS NULL) AND date(time_ref) < date('now', '+7 hours', '-3 days'))
              )
        \"\"\")
        cnt2 = c.rowcount

        # 3. Đối với các đơn chỉ từ nguồn Dispatch (không có inbound, không có Pickup_time)
        #    mà dispatchNetworkTime đã quá 2 ngày → hết hiệu lực
        c.execute(\"\"\"
            UPDATE shipments
            SET is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND data_source = 'Dispatch'
              AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
              AND (outbound_scanDate = '' OR outbound_scanDate IS NULL)
              AND (Pickup_time = '' OR Pickup_time IS NULL)
              AND dispatchNetworkTime != '' AND dispatchNetworkTime IS NOT NULL
              AND datetime(dispatchNetworkTime) < datetime('now', '+7 hours', '-2 days')
        \"\"\")
        cnt3 = c.rowcount
        conn.commit()
        if cnt3 > 0:
            print(f"   🧹 Dọn dẹp Dispatch cũ: Đã tắt {cnt3:,} đơn Dispatch không có inbound/pickup quá 2 ngày.")

        if cnt1 + cnt2 + cnt3 > 0:
            print(f"   🧹 Tự động dọn dẹp: Đã chuyển {cnt1:,} đơn kẹt Inbound → 'Đã rời HUB', tắt {cnt2:,} đơn Forecast/Pickup cũ (>3 ngày), tắt {cnt3:,} đơn Dispatch cũ (>2 ngày).")
            
        c.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows = c.fetchall()
        if rows:
            col_names = [description[0] for description in c.description]
            for r in rows:
                rec = dict(zip(col_names, r))
                db_records[rec['waybillNo']] = rec
        conn.close()
        print(f"   ℹ| Load được {len(db_records):,} đơn active từ SQLite.")
    except Exception as e_db:
        print(f"   ⚠️ Lỗi load đơn từ SQLite: {e_db}")"""

new_load_once = """    # Load active records from PostgreSQL
    db_records = {}
    init_db()
    try:
        conn = psycopg2.connect(**DB_CONN_PARAMS)
        c = conn.cursor()
        
        # Tự động dọn dẹp các đơn kẹt quá 3 ngày không có log xuất kho
        # 1. Đối với các đơn đã quét Inbound
        c.execute(\"\"\"
            UPDATE shipments 
            SET status_order = 'Đã rời HUB', is_active = 0, last_updated = NOW()
            WHERE is_active = 1
              AND (inbound_scandate != '' AND inbound_scandate IS NOT NULL)
              AND CAST(inbound_scandate AS TIMESTAMP) < NOW() - INTERVAL '3 days'
        \"\"\")
        cnt1 = c.rowcount
        
        # 2. Đối với các đơn mới chỉ ở trạng thái Forecast/Pickup (chưa có inbound scan)
        c.execute(\"\"\"
            UPDATE shipments 
            SET is_active = 0, last_updated = NOW()
            WHERE is_active = 1
              AND (inbound_scandate = '' OR inbound_scandate IS NULL)
              AND (
                (pickup_time != '' AND pickup_time IS NOT NULL AND CAST(pickup_time AS TIMESTAMP) < NOW() - INTERVAL '3 days')
                OR
                ((pickup_time = '' OR pickup_time IS NULL) AND CAST(time_ref AS DATE) < CURRENT_DATE - INTERVAL '3 days')
              )
        \"\"\")
        cnt2 = c.rowcount

        # 3. Đối với các đơn chỉ từ nguồn Dispatch (không có inbound, không có pickup_time)
        #    mà dispatchnetworktime đã quá 2 ngày → hết hiệu lực
        c.execute(\"\"\"
            UPDATE shipments
            SET is_active = 0, last_updated = NOW()
            WHERE is_active = 1
              AND data_source = 'Dispatch'
              AND (inbound_scandate = '' OR inbound_scandate IS NULL)
              AND (outbound_scandate = '' OR outbound_scandate IS NULL)
              AND (pickup_time = '' OR pickup_time IS NULL)
              AND dispatchnetworktime != '' AND dispatchnetworktime IS NOT NULL
              AND CAST(dispatchnetworktime AS TIMESTAMP) < NOW() - INTERVAL '2 days'
        \"\"\")
        cnt3 = c.rowcount
        conn.commit()
        if cnt3 > 0:
            print(f"   🧹 Dọn dẹp Dispatch cũ: Đã tắt {cnt3:,} đơn Dispatch không có inbound/pickup quá 2 ngày.")

        if cnt1 + cnt2 + cnt3 > 0:
            print(f"   🧹 Tự động dọn dẹp: Đã chuyển {cnt1:,} đơn kẹt Inbound → 'Đã rời HUB', tắt {cnt2:,} đơn Forecast/Pickup cũ (>3 ngày), tắt {cnt3:,} đơn Dispatch cũ (>2 ngày).")
            
        c.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows = c.fetchall()
        if rows:
            col_names = [description[0] for description in c.description]
            for r in rows:
                rec = pg_row_to_dict(col_names, r)
                db_records[rec['waybillNo']] = rec
        conn.close()
        print(f"   ℹ| Load được {len(db_records):,} đơn active từ PostgreSQL.")
    except Exception as e_db:
        print(f"   ⚠️ Lỗi load đơn từ PostgreSQL: {e_db}")"""
replacements.append((old_load_once, new_load_once, "run_once load & cleanup"))

# ── 9. Replace get_or_create_record ──────────────────────────────
old_get_or_create = """        conn_check = sqlite3.connect(DB_FILE)
        c_check = conn_check.cursor()
        c_check.execute("SELECT * FROM shipments WHERE waybillNo = ?", (wb,))
        row = c_check.fetchone()
        if row:
            col_names = [description[0] for description in c_check.description]
            rec = dict(zip(col_names, row))
            conn_check.close()
            db_records[wb] = rec
            return rec, False
            
        conn_check.close()"""

new_get_or_create = """        conn_check = psycopg2.connect(**DB_CONN_PARAMS)
        c_check = conn_check.cursor()
        c_check.execute("SELECT * FROM shipments WHERE waybillno = %s", (wb,))
        row = c_check.fetchone()
        if row:
            col_names = [description[0] for description in c_check.description]
            rec = pg_row_to_dict(col_names, row)
            conn_check.close()
            db_records[wb] = rec
            return rec, False
            
        conn_check.close()"""
replacements.append((old_get_or_create, new_get_or_create, "get_or_create_record"))

# ── 10. Replace Batch Pickup ─────────────────────────────────────
old_batch_pickup = """                    try:
                        conn_pk = sqlite3.connect(DB_FILE)
                        c_pk    = conn_pk.cursor()
                        updated_pk = 0
                        for wb, pick_name in resolved_pickup.items():
                            c_pk.execute(\"\"\"
                                UPDATE shipments SET pickNetworkName = ?, last_updated = CURRENT_TIMESTAMP
                                WHERE waybillNo = ? AND (pickNetworkName = '' OR pickNetworkName IS NULL)
                            \"\"\", (pick_name, wb))
                            updated_pk += c_pk.rowcount
                        conn_pk.commit()
                        conn_pk.close()
                        print(f"   ✅ [Batch Pickup] Đã cập nhật {updated_pk:,} đơn vào SQLite.")
                    except Exception as e_pk_db:"""

new_batch_pickup = """                    try:
                        conn_pk = psycopg2.connect(**DB_CONN_PARAMS)
                        c_pk    = conn_pk.cursor()
                        updated_pk = 0
                        for wb, pick_name in resolved_pickup.items():
                            c_pk.execute(\"\"\"
                                UPDATE shipments SET picknetworkname = %s, last_updated = NOW()
                                WHERE waybillno = %s AND (picknetworkname = '' OR picknetworkname IS NULL)
                            \"\"\", (pick_name, wb))
                            updated_pk += c_pk.rowcount
                        conn_pk.commit()
                        conn_pk.close()
                        print(f"   ✅ [Batch Pickup] Đã cập nhật {updated_pk:,} đơn vào PostgreSQL.")
                    except Exception as e_pk_db:"""
replacements.append((old_batch_pickup, new_batch_pickup, "Batch Pickup"))

# ── 11. Replace changed_records UPSERT & Reload DB ───────────────
old_upsert_reload = """    if changed_records:
        init_db()
        print(f"\\n💾 Đang lưu {len(changed_records):,} bản ghi thay đổi vào SQLite Database cục bộ...")
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = OFF")
            c.execute("PRAGMA cache_size = -64000")
            c.execute("PRAGMA temp_store = MEMORY")
            
            c.executemany(\"\"\"
                INSERT INTO shipments (
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    is_backlog, is_active, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(waybillNo) DO UPDATE SET
                    data_source        = excluded.data_source,
                    weight             = excluded.weight,
                    pickNetworkName    = excluded.pickNetworkName,
                    dispatch_plan      = excluded.dispatch_plan,
                    Pickup_time        = excluded.Pickup_time,
                    pickup_label       = excluded.pickup_label,
                    Pickup_ontime      = excluded.Pickup_ontime,
                    dispatchNetworkTime= excluded.dispatchNetworkTime,
                    next_station       = excluded.next_station,
                    Tuyến              = excluded.Tuyến,
                    Rank               = excluded.Rank,
                    inbound_network    = excluded.inbound_network,
                    inbound_scanDate   = excluded.inbound_scanDate,
                    outbound_scanDate  = excluded.outbound_scanDate,
                    Arrival_time       = excluded.Arrival_time,
                    dispatch_actual    = excluded.dispatch_actual,
                    status_order       = excluded.status_order,
                    time_ref           = excluded.time_ref,
                    is_backlog         = excluded.is_backlog,
                    is_active          = excluded.is_active,
                    last_updated       = CURRENT_TIMESTAMP
            \"\"\", changed_records)
            conn.commit()
            conn.close()
            print(f"   ✅ Đã UPSERT thành công {len(changed_records)} bản ghi thay đổi vào SQLite.")
        except Exception as ex_db:
            print(f"   ❌ Lỗi lưu dữ liệu thay đổi vào SQLite: {ex_db}")

    # ── Reconcile: Mapping Outbound đã kéo ngược lại DB ──
    # Tái sử dụng results['outbound'] đã kéo ở bước trên → KHÔNG gọi API thêm lần nữa
    try:
        reconcile_outbound_5days(raw_outbound=results.get('outbound', []))
    except Exception as e_reconcile:
        print(f"   ⚠️ Lỗi Reconcile Outbound: {e_reconcile}")


    # ── Reload DB sau khi reconcile để df phản ánh đúng trạng thái mới nhất ──
    try:
        conn_r = sqlite3.connect(DB_FILE)
        c_r    = conn_r.cursor()
        c_r.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows_r = c_r.fetchall()
        if rows_r:
            col_names_r = [d[0] for d in c_r.description]
            db_records  = {dict(zip(col_names_r, rw))['waybillNo']: dict(zip(col_names_r, rw)) for rw in rows_r}
        conn_r.close()
        print(f"   ✅ Reload DB sau reconcile: {len(db_records):,} đơn active còn lại.")
    except Exception as e_reload:
        print(f"   ⚠️ Lỗi reload DB sau reconcile: {e_reload}")"""

new_upsert_reload = """    if changed_records:
        init_db()
        print(f"\\n💾 Đang lưu {len(changed_records):,} bản ghi thay đổi vào PostgreSQL...")
        try:
            conn = psycopg2.connect(**DB_CONN_PARAMS)
            c = conn.cursor()
            
            upsert_query = \"\"\"
                INSERT INTO shipments (
                    waybillno, data_source, weight, picknetworkname, dispatch_plan,
                    pickup_time, pickup_label, pickup_ontime, dispatchnetworktime,
                    next_station, tuyen, rank, inbound_network, inbound_scandate,
                    outbound_scandate, arrival_time, dispatch_actual, status_order, time_ref,
                    is_backlog, is_active
                ) VALUES %s
                ON CONFLICT(waybillno) DO UPDATE SET
                    data_source        = EXCLUDED.data_source,
                    weight             = EXCLUDED.weight,
                    picknetworkname    = EXCLUDED.picknetworkname,
                    dispatch_plan      = EXCLUDED.dispatch_plan,
                    pickup_time        = EXCLUDED.pickup_time,
                    pickup_label       = EXCLUDED.pickup_label,
                    pickup_ontime      = EXCLUDED.pickup_ontime,
                    dispatchnetworktime= EXCLUDED.dispatchnetworktime,
                    next_station       = EXCLUDED.next_station,
                    tuyen              = EXCLUDED.tuyen,
                    rank               = EXCLUDED.rank,
                    inbound_network    = EXCLUDED.inbound_network,
                    inbound_scandate   = EXCLUDED.inbound_scandate,
                    outbound_scandate  = EXCLUDED.outbound_scandate,
                    arrival_time       = EXCLUDED.arrival_time,
                    dispatch_actual    = EXCLUDED.dispatch_actual,
                    status_order       = EXCLUDED.status_order,
                    time_ref           = EXCLUDED.time_ref,
                    is_backlog         = EXCLUDED.is_backlog,
                    is_active          = EXCLUDED.is_active,
                    last_updated       = NOW()
            \"\"\"
            execute_values(c, upsert_query, changed_records)
            conn.commit()
            conn.close()
            print(f"   ✅ Đã UPSERT thành công {len(changed_records)} bản ghi thay đổi vào PostgreSQL.")
        except Exception as ex_db:
            print(f"   ❌ Lỗi lưu dữ liệu thay đổi vào PostgreSQL: {ex_db}")

    # ── Reconcile: Mapping Outbound đã kéo ngược lại DB ──
    # Tái sử dụng results['outbound'] đã kéo ở bước trên → KHÔNG gọi API thêm lần nữa
    try:
        reconcile_outbound_5days(raw_outbound=results.get('outbound', []))
    except Exception as e_reconcile:
        print(f"   ⚠️ Lỗi Reconcile Outbound: {e_reconcile}")


    # ── Reload DB sau khi reconcile để df phản ánh đúng trạng thái mới nhất ──
    try:
        conn_r = psycopg2.connect(**DB_CONN_PARAMS)
        c_r    = conn_r.cursor()
        c_r.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows_r = c_r.fetchall()
        if rows_r:
            col_names_r = [d[0] for d in c_r.description]
            db_records  = {pg_row_to_dict(col_names_r, rw)['waybillNo']: pg_row_to_dict(col_names_r, rw) for rw in rows_r}
        conn_r.close()
        print(f"   ✅ Reload DB sau reconcile: {len(db_records):,} đơn active còn lại.")
    except Exception as e_reload:
        print(f"   ⚠️ Lỗi reload DB sau reconcile: {e_reload}")"""
replacements.append((old_upsert_reload, new_upsert_reload, "UPSERT & Reload DB"))


# ── Run Replacements ──────────────────────────────────────────────
for old, new, desc in replacements:
    # Normalize line endings to avoid discrepancies
    old_norm = old.replace("\\r\\n", "\\n").strip()
    content_norm = content.replace("\\r\\n", "\\n")
    
    if old_norm in content_norm:
        content = content_norm.replace(old_norm, new.strip())
        print(f"✅ Replaced {desc} successfully!")
    else:
        # Fallback to loose strip matching
        old_lines = old_norm.split('\\n')
        first_line = old_lines[0].strip()
        last_line = old_lines[-1].strip()
        print(f"❌ Failed to find exact match for: {desc}")
        print(f"   First line to match: {first_line}")
        print(f"   Last line to match:  {last_line}")

# Save the file
with open(SYNC_SCRIPT_PATH, "w", encoding="utf-8") as f:
    f.write(content)
print("\n🎉 Patching completed!")
