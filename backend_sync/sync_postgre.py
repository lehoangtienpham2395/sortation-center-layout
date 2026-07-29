"""
sync_postgre.py — Dashboard Data Pipeline (3 phần)
====================================================
🌐 Phase 1: Kéo dữ liệu từ JFS API → PostgreSQL
   - pull_dispatch, pull_scan (Inbound/Outbound), pull_arrival, pull_shuttle
   - Dữ liệu được upsert vào enriched.dispatch_enriched

📦 Phase 2: Đọc PostgreSQL → xuất JSON files cho dashboard React
   - inventory.json, outbound.json, backlog.json, inbound.json,
     arrival.json, heatmap.json, linehaul.json, truck_eta.json,
     hub_inventory_pivot.json, last_update.json, latest.json.gz

🚀 Phase 3: Git commit + push lên GitHub
   - `git add data/ src/`
   - `git commit -m "chore(data): auto-sync [timestamp]"`
   - `git push origin main`

Field names: 100% English snake_case.
"""

import os, sys, io, json, gzip, datetime, time as _time, threading, math, subprocess
from zoneinfo import ZoneInfo

# ── UTF-8 stdout ─────────────────────────────────────────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)

# ── Resolve paths ─────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "data")
VALID_FILE = os.path.join(BASE_DIR, "backend_sync", "config", "valid.csv")
CONTRACT_FILE = os.path.join(BASE_DIR, "backend_sync", "config", "data_contract.json")

DATA_CONTRACT = {}
if os.path.exists(CONTRACT_FILE):
    try:
        with open(CONTRACT_FILE, "r", encoding="utf-8") as _cf:
            DATA_CONTRACT = json.load(_cf)
        print("✅ Data Contract loaded successfully")
    except Exception as _ce:
        print(f"⚠️ Failed to load Data Contract: {_ce}")

# pipeline_unified_v6.py nằm ở thư mục cha của repo (scratch)
PIPELINE_DIR = os.path.dirname(BASE_DIR)
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

# ── Import từ pipeline_unified_v6 ─────────────────────────────────────────────
try:
    import importlib, pandas as pd
    _pv6 = importlib.import_module("pipeline_unified_v6")
    build_session        = _pv6.build_session
    TokenManager         = _pv6.TokenManager
    auth_post            = _pv6.auth_post
    pull_linehaul_consol = _pv6.pull_linehaul_consol
    pull_shuttle         = _pv6.pull_shuttle
    pull_arrival         = _pv6.pull_arrival
    ACCOUNT              = _pv6.ACCOUNT
    PASSWORD             = _pv6.PASSWORD
    ARR_ACCOUNT          = _pv6.ARR_ACCOUNT
    ARR_PASSWORD         = _pv6.ARR_PASSWORD
    COUNTRY_ID           = _pv6.COUNTRY_ID
    _HAS_PIPELINE        = True
    print("✅ pipeline_unified_v6 imported OK")
except Exception as _e:
    _HAS_PIPELINE = False
    print(f"⚠️  pipeline_unified_v6 import failed: {_e} — JFS API disabled")
    try:
        import pandas as pd
    except ImportError:
        pass

# ── PostgreSQL ────────────────────────────────────────────────────────────────
PG_DBNAME = os.environ.get("PGDATABASE", "logistics_db")
PG_USER   = os.environ.get("PGUSER",     "postgres")
PG_PASS   = os.environ.get("PGPASSWORD", "Tien@giang0203")
PG_HOST   = os.environ.get("PGHOST",     "127.0.0.1")
PG_PORT   = int(os.environ.get("PGPORT", 5433))

def is_valid_ts(val) -> bool:
    if val is None or pd.isna(val):
        return False
    s = str(val).strip()
    if not s or s.lower() in ('nat', 'none', 'nan', 'null'):
        return False
    return True

def clean_ts_str(val) -> str:
    if not is_valid_ts(val):
        return ""
    try:
        if isinstance(val, (pd.Timestamp, datetime.datetime)):
            if val.tzinfo is not None:
                val = val.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
            return val.strftime("%Y-%m-%d %H:%M:%S")
        s = str(val).strip()
        if '+00' in s or s.endswith('Z'):
            dt = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
            dt_vn = dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
            return dt_vn.strftime("%Y-%m-%d %H:%M:%S")
        return s
    except Exception:
        return str(val).strip()

# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
tz_vn     = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn    = datetime.datetime.now(tz_vn)
today     = now_vn.strftime("%Y-%m-%d")
yesterday = (now_vn - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
tomorrow  = (now_vn + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
now_sys   = now_vn.strftime("%Y-%m-%d %H:%M:%S")
start_str = (now_vn - datetime.timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
end_str   = now_vn.strftime("%Y-%m-%d %H:%M:%S")
end_plus1 = (now_vn + datetime.timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")


# ════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════

def get_op_date(dt_str: str) -> str:
    """Ngày vận hành theo cycle 06:00–06:00."""
    if not dt_str or str(dt_str).lower() in ('nan', 'none', ''):
        return ""
    try:
        dt = datetime.datetime.strptime(str(dt_str)[:19], '%Y-%m-%d %H:%M:%S')
        if dt.hour < 6:
            return (dt.date() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return str(dt_str)[:10]


def clean_status_sys(status_raw) -> str:
    """
    Chuẩn hoá 100% alias trạng thái thô từ JFS API thành 5 enum chuẩn dựa trên Data Contract:
    'Inbound', 'Transporting', 'Pickup Done', 'Created', 'Outbound' (hoặc 'Đã hủy')
    """
    if status_raw is None or pd.isna(status_raw):
        return 'Created'
    st = str(status_raw).strip()
    
    aliases = DATA_CONTRACT.get("enums", {}).get("status", {}).get("aliases", {})
    if st in aliases:
        return aliases[st]
    st_lower = st.lower()
    if st_lower in aliases:
        return aliases[st_lower]
    
    if any(kw in st_lower for kw in ['đã hủy', 'cancelled', 'canceled', 'hủy']):
        return 'Đã hủy'
    if any(kw in st_lower for kw in ['đã xuất kho', 'outbound', 'outbound_done', 'đã xuất khỏi hub']):
        return 'Outbound'
    if any(kw in st_lower for kw in ['đã nhập kho', 'inbound', 'inbound_done', 'đang trên bãi']):
        return 'Inbound'
    if any(kw in st_lower for kw in ['đang vận chuyển', 'transporting', 'in_transit', 'chưa đến hub']):
        return 'Transporting'
    if any(kw in st_lower for kw in ['đã lấy hàng', 'pickup done', 'pickup_done', 'picked_up']):
        return 'Pickup Done'
    
    return st or 'Created'


def validate_payload_contract(records: list, dataset_name: str) -> None:
    """Xác minh 100% payload tuân thủ Hợp đồng Dữ liệu (Display-Ready & Canonical Enums)."""
    canonical_statuses = set(DATA_CONTRACT.get("enums", {}).get("status", {}).get("canonical", []))
    if not canonical_statuses or not records:
        return
    invalid_count = 0
    for r in records:
        st = r.get("status")
        if st and st not in canonical_statuses:
            invalid_count += 1
    if invalid_count == 0:
        print(f"   🛡️  [Data Contract] {dataset_name:<30}: 100% VALID (Display-Ready Canonical Enums)")
    else:
        print(f"   ⚠️  [Data Contract] {dataset_name:<30}: {invalid_count} records non-canonical status")


def get_or_create_daily_baseline(conn, today_date_str: str) -> int:
    """
    Tạo và đọc baseline rot_hom_truoc tại 06:00 AM mỗi ngày trong PostgreSQL.
    Bảng: enriched.daily_baseline_snapshot
    """
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS enriched.daily_baseline_snapshot (
                op_date DATE PRIMARY KEY,
                rot_hom_truoc_count INT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        cur.execute("""
            SELECT COUNT(*) FROM enriched.dispatch_enriched
            WHERE (inbound_scandate IS NULL)
              AND (outbound_scandate IS NULL)
              AND (flag_pickup = 1 OR pickup_time IS NOT NULL OR arrival_scandate IS NOT NULL)
              AND (next_station IS NULL OR next_station <> 'Đã hủy')
              AND (status_sys IS NULL OR status_sys <> 'Đã hủy')
              AND (is_rebound IS NULL OR is_rebound = 0)
              AND (
                (op_date_pickup IS NOT NULL AND op_date_pickup < %s::date)
                OR (op_date_pickup IS NULL AND operation_date_created < %s::date)
              );
        """, (today_date_str, today_date_str))
        calc_val = cur.fetchone()[0] or 0

        cur.execute("""
            INSERT INTO enriched.daily_baseline_snapshot (op_date, rot_hom_truoc_count)
            VALUES (%s, %s)
            ON CONFLICT (op_date) DO UPDATE SET rot_hom_truoc_count = EXCLUDED.rot_hom_truoc_count;
        """, (today_date_str, calc_val))
        conn.commit()
        cur.close()
        print(f"   📌 Baseline Rớt Hôm Trước (chốt 06:00 AM cho ngày {today_date_str}, ĐÃ PICKUP, CHƯA INBOUND): {calc_val:,} đơn")
        return calc_val
    except Exception as e:
        print(f"   ⚠️  Không thể lưu/đọc baseline snapshot: {e}")
        return 0


def write_json(filename: str, obj) -> None:
    """Ghi JSON UTF-8, không escape unicode."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(path) // 1024
    n = len(obj) if isinstance(obj, (list, dict)) else 1
    print(f"   ✅ {filename:<42} {size_kb:>6} KB  |  {n:,} records")


def get_pg_conn():
    import psycopg2
    return psycopg2.connect(
        dbname=PG_DBNAME, user=PG_USER, password=PG_PASS,
        host=PG_HOST, port=PG_PORT, connect_timeout=15,
        options='-c statement_timeout=30000'
    )


def get_sa_engine():
    """SQLAlchemy engine for pd.read_sql (tránh UserWarning DBAPI2)."""
    try:
        from sqlalchemy import create_engine
        return create_engine(
            f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}",
            connect_args={'connect_timeout': 15, 'options': '-c statement_timeout=30000'},
            pool_pre_ping=True,
        )
    except ImportError:
        return None  # Fallback: caller will use raw psycopg2 conn


def refresh_operational_flags() -> None:
    """
    Atomic UPDATE: Tinh lai toan bo 7 cot co + helper cho Pool 1 + Pool 2 (rows vua duoc upsert).
    Goi ngay sau Phase 1, truoc Phase 2 de dam bao JSON luon doc flag chinh xac.

    Nguyen tac an toan:
    - flag_backlog KHONG luu — tinh inline trong query (WHERE flag_inbound=1 AND flag_outbound=0)
    - flag_rot_nay / flag_rot_truoc KHONG luu — tinh dong trong SQL voi op_today tu Python
    - Tat ca flag khac duoc reset nguyen tu (atomic) trong 1 UPDATE duy nhat
    """
    print("   🔄 Refreshing operational flags (atomic)...")
    t_start = _time.time()
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE enriched.dispatch_enriched SET
                flag_created   = 1,
                flag_pickup    = CASE WHEN pickup_time IS NOT NULL     THEN 1 ELSE 0 END,
                flag_arrival   = CASE WHEN arrival_scandate IS NOT NULL THEN 1 ELSE 0 END,
                flag_inbound   = CASE
                                    WHEN inbound_scandate IS NOT NULL THEN 1
                                    WHEN is_rebound = 1 AND inbound_scandate_2 IS NOT NULL THEN 1
                                    ELSE 0 END,
                flag_outbound  = CASE
                                    WHEN outbound_scandate IS NOT NULL THEN 1
                                    WHEN is_rebound = 1 AND outbound_scandate_2 IS NOT NULL THEN 1
                                    ELSE 0 END,
                -- Helper: ngay pickup theo boundary 06:00 (dung tinh rot dong trong SQL)
                op_date_pickup = CASE
                                    WHEN pickup_time IS NULL THEN NULL
                                    WHEN EXTRACT(HOUR FROM pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                                    THEN (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                                    ELSE (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                                 END,
                -- Helper: ngay Inbound chinh xac cho Rebound (fix Rui ro 3)
                op_date_inbound_effective = CASE
                                    WHEN is_rebound = 1 AND operation_date_inbound_2 IS NOT NULL
                                    THEN operation_date_inbound_2
                                    ELSE operation_date_inbound
                                 END
            WHERE
                -- Pool 1: moi don dang active (bao gom Rebound, Rot chua ve HUB)
                is_active = 1 OR is_completed = FALSE
                -- Pool 2: don da hoan thanh nhung co thao tac moi trong 2 ngay
                OR last_updated >= NOW() - INTERVAL '2 days'
        """)
        updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        print(f"   ✅ Flags refreshed: {updated:,} rows ({_time.time()-t_start:.1f}s)")
    except Exception as e:
        print(f"   ⚠️  Flag refresh error (non-fatal): {e}")


# ════════════════════════════════════════════════════════════════════
# JFS LINEHAUL + TRUCK ETA (dùng pipeline_unified_v6 functions)
# ════════════════════════════════════════════════════════════════════

def fetch_linehaul_json(session, token_mgr) -> dict:
    """
    Gọi pull_linehaul_consol → chuẩn hóa → dict JSON schema:
    {
      "generated_at": "...",
      "total_trucks": N,
      "trucks": [{
        "plate_number", "carrier_name", "send_network", "arrive_network",
        "trip_code", "orders_count", "weight_kg", "weight_ton",
        "planned_departure", "planned_arrival",
        "actual_departure", "actual_arrival", "eta",
        "rank", "status", "op_date"
      }]
    }
    """
    try:
        recs = pull_linehaul_consol(session, token_mgr, start_str, end_plus1)
    except Exception as e:
        print(f"   ⚠️  pull_linehaul_consol failed: {e}")
        recs = []

    seen = {}
    for row in recs:
        tc         = str(row.get('shipmentName') or row.get('shipmentNo') or '').strip().upper()
        actual_arr = str(row.get('actualArrivalTime')    or '').strip()
        actual_dep = str(row.get('actualDepartureTime')  or '').strip()
        weight_kg  = float(row.get('loadpackageweight')  or 0)
        status     = 'arrived' if actual_arr else ('in_transit' if actual_dep else 'loading')
        op_d       = get_op_date(actual_arr or actual_dep or now_sys)
        entry = {
            "plate_number":     str(row.get('plateNumber')          or '').strip(),
            "carrier_name":     str(row.get('carrierName')          or '').strip(),
            "send_network":     str(row.get('sendNetworkName')       or '').strip(),
            "arrive_network":   str(row.get('arriveNetworkName')     or '').strip(),
            "trip_code":        tc,
            "orders_count":     int(row.get('loadscanwaybillnum')    or 0),
            "weight_kg":        weight_kg,
            "weight_ton":       round(weight_kg / 1000, 3),
            "planned_departure":str(row.get('plannedDepartureTime')  or '').strip(),
            "planned_arrival":  str(row.get('plannedArrivalTime')    or '').strip(),
            "actual_departure": actual_dep,
            "actual_arrival":   actual_arr,
            "eta":              str(row.get('predictArriveTime')     or '').strip(),
            "rank":             "Linehaul",
            "status":           status,
            "op_date":          op_d,
        }
        # Chỉ giữ lại các chuyến xe thuộc ca hôm nay hoặc hôm qua (bỏ các chuyến xe cũ từ nhiều ngày trước)
        if op_d in (today, yesterday):
            if tc not in seen or (actual_arr and not seen[tc].get('actual_arrival')):
                seen[tc] = entry

    trucks = sorted(seen.values(), key=lambda x: x.get('actual_arrival') or x.get('planned_arrival') or '', reverse=True)
    print(f"   ✅ Linehaul: {len(trucks)} trips")
    return {"generated_at": now_sys, "total_trucks": len(trucks), "trucks": trucks}


def fetch_truck_eta_json(session, token_mgr) -> dict:
    """
    Tạo danh sách Truck ETA (xe đang về / chờ nhập kho HCM HUB) từ 2 nguồn:
      1. PostgreSQL dispatch_enriched: các bưu cục có đơn đã Pickup/Arrival nhưng chưa Inbound.
      2. JFS API pull_shuttle & pull_linehaul_consol: các chuyến xe thực tế có sản lượng > 0.
    Loại bỏ hoàn toàn các 423 lịch trình chuyến rỗng (orders_count = 0).
    """
    trucks = []
    seen_keys = set()

    # ── 1. PostgreSQL DB: Gom các bưu cục/chuyến thực tế đang có đơn vận chuyển về HUB ──
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COALESCE(NULLIF(TRIM(pickup_station), ''), 'KHÔNG XÁC ĐỊNH') as send_net,
                'HCM HUB' as arr_net,
                COALESCE(NULLIF(TRIM(trip_code), ''), 'DIRECT') as trip_c,
                COUNT(*) as vol,
                ROUND((SUM(orders_weight) / 1000.0)::numeric, 2) as wt_kg,
                MAX(arrival_scandate) as max_arr,
                MAX(transporing_time) as max_transp
            FROM enriched.dispatch_enriched
            WHERE flag_inbound = 0 
              AND (flag_arrival = 1 OR flag_pickup = 1)
              AND (is_completed = FALSE OR is_active = 1)
            GROUP BY send_net, trip_c
            HAVING COUNT(*) > 0
            ORDER BY vol DESC;
        """)
        rows = cur.fetchall()
        conn.close()

        for r in rows:
            send_st, arr_st, trip, vol, wt_kg, max_arr, max_transp = r
            ref_t = str(max_arr or max_transp or '')[:16]
            op_d = get_op_date(ref_t) if ref_t else today

            if op_d in (today, yesterday):
                key = (send_st, trip)
                seen_keys.add(key)
                trucks.append({
                    "send_network":     send_st,
                    "arrive_network":   arr_st,
                    "trip_code":        trip,
                    "orders_count":     int(vol),
                    "weight_kg":        float(wt_kg),
                    "weight_ton":       round(float(wt_kg) / 1000.0, 3),
                    "planned_departure":ref_t,
                    "planned_arrival":  ref_t,
                    "actual_departure": ref_t,
                    "eta":              ref_t,
                    "rank":             "Shuttle",
                    "status":           "arrived" if max_arr else "in_transit",
                    "op_date":          op_d,
                })
    except Exception as e:
        print(f"   ⚠️ PostgreSQL truck_eta aggregation error: {e}")

    # ── 2. JFS API: Bổ sung các chuyến shuttle có đơn thực tế (orders_count > 0) ──
    try:
        today_start = today + ' 00:00:00'
        recs = pull_shuttle(session, token_mgr, today_start, end_plus1)
        for row in recs:
            actual_arr = str(row.get('actualArrivalTime') or '').strip()
            if actual_arr:
                continue

            orders_cnt = int(row.get('loadscanwaybillnum') or row.get('waybillNum') or 0)
            if orders_cnt <= 0:
                continue  # Bỏ qua 423 khung lịch trình rỗng không có đơn

            p_dep = str(row.get('plannedDepartureTime') or row.get('createTime') or '').strip()
            actual_dep = str(row.get('actualDepartureTime') or row.get('appDepartureTime') or '').strip()
            trip = str(row.get('shipmentNo') or row.get('taskNo') or '').strip().upper()
            send_net = str(row.get('sendNetworkName') or row.get('startName') or '').strip()
            arr_net  = str(row.get('arriveNetworkName') or row.get('endName') or '').strip()

            key = (send_net, trip)
            if key not in seen_keys:
                seen_keys.add(key)
                ref_t = actual_dep or p_dep
                op_d = get_op_date(ref_t) if ref_t else today
                if op_d in (today, yesterday):
                    wt_kg = float(row.get('loadpackageweight') or 0)
                    trucks.append({
                        "send_network":     send_net,
                        "arrive_network":   arr_net,
                        "trip_code":        trip,
                        "orders_count":     orders_cnt,
                        "weight_kg":        wt_kg,
                        "weight_ton":       round(wt_kg / 1000.0, 3),
                        "planned_departure":p_dep,
                        "planned_arrival":  str(row.get('plannedArrivalTime') or '').strip(),
                        "actual_departure": actual_dep,
                        "eta":              str(row.get('estimateArrivalTime') or '').strip(),
                        "rank":             "Shuttle",
                        "status":           "in_transit" if actual_dep else "loading",
                        "op_date":          op_d,
                    })
    except Exception as e:
        print(f"   ⚠️ pull_shuttle API call skipped/failed: {e}")

    trucks.sort(key=lambda x: x.get('orders_count', 0), reverse=True)
    print(f"   ✅ Truck ETA (en route real orders): {len(trucks)} active trucks/trips")
    return {"generated_at": now_sys, "total_trucks_en_route": len(trucks), "trucks": trucks}


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

def sync_postgre_to_dashboard():
    t0 = _time.time()
    print(f"\n🚀 [{now_sys}] sync_postgre_to_dashboard()")
    print(f"   DB      : {PG_DBNAME} @ {PG_HOST}:{PG_PORT}")
    print(f"   Data    : {DATA_DIR}")
    print(f"   Today   : {today}  |  Yesterday: {yesterday}")
    print("=" * 60)

    # ── 1. Load valid.csv (Master Config từ Google Sheet) ─────────
    dict_zone, dict_area, dict_station = {}, {}, {}
    if os.path.exists(VALID_FILE):
        df_v = pd.read_csv(VALID_FILE, dtype=str)
        df_v.columns = df_v.columns.str.strip()
        sc_col   = next((c for c in ['sortcode', 'Mã trạm', 'Dispatch_code'] if c in df_v.columns), None)
        area_col = next((c for c in ['area', 'AreaID'] if c in df_v.columns), None)
        st_col   = next((c for c in ['Bưu cục', 'Station_1', 'Station_2'] if c in df_v.columns), None)
        zone_col = next((c for c in ['Zone', 'Hubcode'] if c in df_v.columns), None)

        if sc_col and area_col:
            sc = df_v[sc_col].dropna().str.strip().str.upper()
            if zone_col: dict_zone = dict(zip(sc, df_v[zone_col].fillna('3').str.strip()))
            dict_area = dict(zip(sc, df_v[area_col].fillna('C01').str.strip()))
            if st_col:   dict_station = dict(zip(sc, df_v[st_col].fillna('').str.strip()))
            print(f"   valid.csv : {len(dict_area):,} sortcodes (Master Google Sheet Config)")
        elif area_col and st_col:
            for _, r_v in df_v.iterrows():
                a_id = str(r_v.get(area_col) or '').strip()
                b_c  = str(r_v.get(st_col) or '').strip()
                z_n  = str(r_v.get(zone_col) or '3').strip()
                if a_id:
                    dict_area[a_id] = a_id
                    dict_station[a_id] = b_c
                    dict_zone[a_id] = z_n
            print(f"   valid.csv : {len(dict_area):,} AreaIDs (Master Google Sheet Config)")
    else:
        print(f"   ⚠️  valid.csv not found — zone/area mapping empty")

    # ── Phase 1: JFS API → PostgreSQL (import trực tiếp pipeline_unified_v6.py) ──
    _etl_dir = os.path.dirname(os.path.abspath(__file__))  # backend_sync/
    if _etl_dir not in sys.path:
        sys.path.insert(0, _etl_dir)
    try:
        import pipeline_unified_v6 as _pipe6
        print("\n🌐 Phase 1: JFS API → PostgreSQL (pipeline_unified_v6.main())...")
        t1 = _time.time()
        _pipe6.main()
        print(f"   ✅ Phase 1 xong ({_time.time()-t1:.0f}s) — PostgreSQL đã cập nhật")
    except Exception as _e1:
        print(f"   ⚠️  Phase 1 error: {_e1} — tiếp tục Phase 2 từ DB hiện tại")

    # ── Phase 1.5: Atomic flag refresh (sau upsert, trước export JSON) ────────────
    # Bảo đảm flag_inbound/outbound/pickup/arrival luôn nhất quán với timestamp gốc
    refresh_operational_flags()

    # ── 2. PostgreSQL fetch & export ──────────────────────────────────────────
    print("\n📦 Phase 2: Reading from PostgreSQL logistics_db & generating JSONs...")

    query = """
        SELECT
            tracking, status_sys, created_time,
            pickup_station, dispatch_code,
            orders_num, orders_weight,
            pickup_station2, pickup_time,
            areacode, flowtypedesc, next_station,
            round, rank,
            inbound_scandate, outbound_scandate, arrival_scandate,
            trip_code, transporing_time, transported_time,
            operation_date_created, operation_date_inbound,
            is_backlog, is_active,
            is_completed, cycle_no, is_rebound, return_count,
            inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
            -- Operational Flags (atomic-refreshed sau Phase 1)
            flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound,
            -- Helper columns (fix Rui ro 2 & 3)
            op_date_pickup,                -- Dung tinh rot dong (flag_rot_nay/truoc)
            op_date_inbound_effective      -- Ngay inbound chinh xac cho Rebound
        FROM enriched.dispatch_enriched
        ORDER BY operation_date_created DESC, created_time DESC
    """
    try:
        sa_engine = get_sa_engine()
        if sa_engine:
            df = pd.read_sql(query, sa_engine)
            sa_engine.dispose()
            print("   🟢 Connected to PostgreSQL (SQLAlchemy)")
        else:
            # Fallback nếu sqlalchemy chưa cài
            import warnings
            conn = get_pg_conn()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                df = pd.read_sql(query, conn)
            conn.close()
            print("   🟢 Connected to PostgreSQL (psycopg2 fallback)")
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        return

    if len(df) == 0:
        print("   ⚠️  0 rows — aborting to protect existing files")
        return

    df = df.fillna('')
    total_rows = len(df)
    today_rows = len(df[df['operation_date_created'].astype(str).str[:10] == today])
    print(f"   📦 {total_rows:,} records từ PostgreSQL (2 ngày gần nhất)")
    print(f"   📅 Ngày vận hành hôm nay ({today}): {today_rows:,} đơn")
    print(f"   📅 Ngày hôm qua ({yesterday})       : {total_rows - today_rows:,} đơn")

    # ── 3. Aggregate ──────────────────────────────────────────────
    inv_group     = {}   # (zone, area_id, station_name, status) → {volume, weight_kg, capacity}
    out_group     = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    backlog_group = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    inbound_group = {}   # 14-tuple key                          → {volume, weight_kg}
    arr_group     = {}   # (op_date, station_name, scan_hour)    → {total, at_hub, not_hub, last_scan_time}
    hourly        = {f"{h:02d}:00": 0 for h in range(24)}

    # ── Cờ Rớt đơn (Nguyên tắc 6) ────────────────────────────────
    # Baseline chốt 06:00 AM cho Inbound Dashboard (bất biến)
    rot_hom_truoc_baseline = 0
    try:
        conn_b = get_pg_conn()
        rot_hom_truoc_baseline = get_or_create_daily_baseline(conn_b, today)
        conn_b.close()
    except Exception as _eb:
        print(f"   ⚠️ Baseline query error: {_eb}")

    rot_hom_truoc = 0   # Pickup hôm trước, chưa về HUB → live dynamic tracking cho Layout Volume
    rot_hom_nay   = 0   # Pickup hôm nay, chưa về HUB  → đang trên đường
    ZONE_MAP = {'SR0001': '1', 'BNI001': '1', '1': '1', '2': '2', '3': '3'}

    # Bảng quy hoạch layout ô chứa chuẩn từ Google Sheets người dùng cấp
    OFFICIAL_LAYOUT_MAP = {
        'C24': ('BD BÌNH HÒA', '3'), 'C23': ('SG BẢY HIỀN', '3'), 'C12': ('SG PHÚ NHUẬN', '3'),
        'C21': ('AG THOẠI SƠN', '3'), 'C20': ('AG TỊNH BIÊN', '3'), 'C19': ('AG TÂN CHÂU', '3'),
        'C18': ('AG AN PHÚ', '3'), 'C17': ('VL CHỢ LÁCH', '3'), 'C16': ('SG NHƠN ĐỨC', '3'),
        'C15': ('ST PHÚ LỢI', '3'), 'C14': ('CT LONG MỸ', '3'), 'C13': ('ST VĨNH CHÂU', '3'),
        'B10': ('SG GÒ VẤP', '3'), 'C25': ('LA BẾN LỨC', '3'), 'C10': ('SG XUÂN HÒA', '3'),
        'C09': ('LA HẬU NGHĨA', '3'), 'C08': ('TG GÒ CÔNG', '3'), 'X': ('DT TN', '3'),
        'C06': ('BD DĨ AN', '3'), 'C05': ('SG KHÁNH HỘI', '3'), 'C04': ('SG BÌNH TRỊ ĐÔNG', '3'),
        'C03': ('SG BÌNH LỢI TRUNG', '3'), 'C02': ('SG HƯNG LONG', '3'), 'C01': ('SG CHỢ LỚN', '3'),
        'B15': ('SG TÂN NHỰT', '2'), 'B14': ('SG VĨNH LỘC', '2'), 'B13': ('VT XUYÊN MỘC', '2'),
        'B12': ('VT CHÂU ĐỨC', '2'), 'B11': ('SG AN PHÚ ĐÔNG', '2'), 'A03': ('SG TÂN THỚI HIỆP', '2'),
        'B09': ('SG TÂN TẠO', '2'), 'B08': ('SG CỦ CHI', '2'), 'B07': ('SG TÂN SƠN NHÌ', '2'),
        'B06': ('SG HIỆP BÌNH', '2'), 'B05': ('SG PHÚ LÂM', '2'), 'B04': ('SG AN LẠC', '2'),
        'B03': ('SG BÌNH TÂN', '2'), 'B02': ('SG TÂN HƯNG', '2'), 'B01': ('SG ĐÔNG HƯNG THUẬN', '2'),
        'A20': ('AG CẦN ĐĂNG', '1'), 'A19': ('AG LONG XUYÊN', '1'), 'A18': ('VT VŨNG TÀU', '1'),
        'A17': ('TG TRUNG AN', '1'), 'A15': ('LA TÂN AN', '1'), 'A14': ('TG AN HỮU', '1'),
        'A13': ('VL VĨNH LONG', '1'), 'A12': ('TG HÒA KHÁNH', '1'), 'A11': ('DT SA ĐÉC', '1'),
        'A10': ('DT CAO LÃNH', '1'), 'A09': ('CT NINH KIỀU', '1'), 'A08': ('CT BÌNH THỦY', '1'),
        'A07': ('CT Ô MÔN', '1'), 'A06': ('BN HUB', '1'), 'A04': ('LA ĐỨC HÒA', '3'),
        'A16': ('SG THỦ ĐỨC', '3'), 'A02': ('SG BÌNH LỢI', '3'), 'A01': ('SG HÓC MÔN', '3'),
        'C22': ('VT LONG ĐẤT', '3'), 'C26': ('SE TN', '3'), 'C11': ('LA CẦN ĐƯỚC', '3'),
        'B16': ('SG BÀ ĐIỂM', '2')
    }

    OFFICIAL_STATION_TO_AREA = {v[0].upper(): k for k, v in OFFICIAL_LAYOUT_MAP.items()}

    for _, r in df.iterrows():
        pk_st_raw = str(r.get('pickup_station', '')).strip()
        sc_raw    = str(r.get('dispatch_code', '')).strip().upper()
        sc        = sc_raw
        next_st   = str(r.get('next_station',  '')).strip()
        mapped_st = dict_station.get(sc, '')
        
        # 🎯 INVENTORY LOGIC: Categorized strictly by Next_station (Bưu cục đích)
        # Uu tien 1: Next station (Buu cuc dich) -> Uu tien 2: Mapped station tu sortcode -> Uu tien 3: Pickup station (Buu cuc nguon)
        target_st = next_st if (next_st and next_st not in ('', 'KHÔ VÙNG KHÁC')) else (mapped_st or pk_st_raw)
        target_st_upper = target_st.strip().upper()

        if target_st_upper in OFFICIAL_STATION_TO_AREA:
            area_id = OFFICIAL_STATION_TO_AREA[target_st_upper]
            station = OFFICIAL_LAYOUT_MAP[area_id][0]
            zone    = OFFICIAL_LAYOUT_MAP[area_id][1]
        elif sc and dict_area.get(sc):
            area_id = dict_area.get(sc)
            station = dict_station.get(sc, target_st)
            zone    = ZONE_MAP.get(dict_zone.get(sc, '3'), '3')
        else:
            station = target_st or 'KHÔ VÙNG KHÁC'
            area_id = OFFICIAL_STATION_TO_AREA.get(station.upper(), 'C01')
            zone    = OFFICIAL_LAYOUT_MAP.get(area_id, ('', '3'))[1]

        valid_area = bool(area_id)
        cap      = 1400 if area_id == 'A06' else 780
        raw_wt   = float(r.get('orders_weight') or 0)
        wt_kg    = (raw_wt / 1000.0) if raw_wt > 500.0 else raw_wt
        cr_t     = clean_ts_str(r.get('created_time'))
        pk_t     = clean_ts_str(r.get('pickup_time'))
        inb_t    = clean_ts_str(r.get('inbound_scandate'))
        outb_t   = clean_ts_str(r.get('outbound_scandate'))
        arr_t    = clean_ts_str(r.get('arrival_scandate'))
        trip     = str(r.get('trip_code',           '')).strip()
        transp_t = clean_ts_str(r.get('transporing_time'))
        transpd_t= clean_ts_str(r.get('transported_time'))
        op_date  = str(r.get('operation_date_created', today))[:10] or today

        has_in   = bool(inb_t)
        has_out  = bool(outb_t)
        has_arr  = bool(arr_t)
        has_pick = bool(pk_t)

        is_reb    = int(r.get('is_rebound') or 0)
        ret_cnt   = int(r.get('return_count') or 0)
        inb_t_2   = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t_2  = clean_ts_str(r.get('outbound_scandate_2'))
        op_inb_2  = str(r.get('operation_date_inbound_2') or '')[:10]
        has_out_2 = bool(outb_t_2)

        # Dynamic Rot calculation theo tiêu chí USER:
        # - Tất cả đơn CHƯA NHẬP KHO (flag_inb=0), trừ Đã hủy/Rebound, đều là ĐƠN RỚT CHƯA VỀ HUB
        # - Rớt Hôm Nay   : Thuộc ca today (op_pk == today hoặc op_cr == today) - bao gồm cả Pickup, Arrival, Transporting
        # - Rớt Hôm Trước : Thuộc ca các ngày trước (< today) - gối đầu tồn
        #
        # ⚠️ HỢP ĐỒNG DỮ LIỆU: drop_type xuất ra giá trị HIỂN THỊ SẴN (display-ready),
        # y hệt cách `status`/`inv_status` bên dưới đang làm — để khớp trực tiếp với
        # chuỗi so sánh cứng trong src/components/InboundDashboard.tsx
        # (ví dụ: d['Loại rớt'] === 'Rớt hôm nay'). Nếu đổi giá trị ở đây, PHẢI đổi
        # đồng thời BACKEND_DROP_TYPE_MAP trong src/App.tsx để 2 bên không bị lệch nữa.
        DROP_TYPE_TODAY     = 'Rớt hôm nay'
        DROP_TYPE_YESTERDAY = 'Rớt hôm trước'

        stn = str(r.get('next_station', '')).strip()
        is_canceled = (stn == 'Đã hủy' or r.get('status_sys') == 'Đã hủy')
        is_rot = (not has_in) and (not is_canceled) and (not is_reb)

        ref_rot_date = str(r.get('op_date_pickup') or get_op_date(cr_t) or op_date or '')[:10]
        if is_rot:
            if ref_rot_date == today:
                rot_hom_nay   += 1
                drop_type = DROP_TYPE_TODAY
            else:
                rot_hom_truoc += 1
                drop_type = DROP_TYPE_YESTERDAY
        else:
            drop_type = ''

        # Trạng thái Rebound đang tồn bãi thực tế (Đã quay đầu nhập kho Lần 2 mà chưa xuất kho Lần 2)
        is_active_rebound = (is_reb == 1 and not has_out_2)

        # Đơn hiện tại đang NẰM TẠI KHO (chưa xuất kho lần 1, HOẶC đã Rebound quay đầu về kho mà chưa xuất kho lần 2)
        is_currently_at_hub = (not has_out) or is_active_rebound

        st_sys_raw = str(r.get('status_sys', '')).strip()
        has_pk = bool(r.get('flag_pickup') or pk_t or st_sys_raw in ('Đã lấy hàng', 'Pickup Done', 'pickup_done'))

        # Inventory status (trùng khớp 100% với bộ lọc Control Center trong React UI)
        # ⚠️ HỢP ĐỒNG DỮ LIỆU: đây là giá trị HIỂN THỊ SẴN (display-ready), phải khớp
        # chính xác (kể cả hoa/thường) với danh sách INVENTORY_STATUSES trong src/App.tsx
        # và BACKEND_STATUS_MAP dùng để chuẩn hoá dữ liệu. Nếu đổi giá trị ở đây,
        # PHẢI đổi đồng thời bên frontend — nếu không dashboard sẽ lại sai âm thầm
        # (không báo lỗi) giống lỗi drop_type đã từng gặp.
        inv_status = ('Inbound'      if is_active_rebound else
                      'Outbound'     if (has_out and not is_active_rebound) else
                      'Inbound'      if has_in  else
                      'Transporting' if has_arr else
                      'Pickup Done'  if has_pk else 'Created')

        # 1. inventory group — Đơn hiện ĐANG TỒN TẠI KHO và có area_id hợp lệ
        if is_currently_at_hub and valid_area:
            ki = (zone, area_id, station, inv_status)
            if ki not in inv_group:
                inv_group[ki] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            inv_group[ki]['volume']    += 1
            inv_group[ki]['weight_kg'] += wt_kg

        # 2. outbound group — đơn đã xuất kho hoàn tất (Lần 1 hoặc Lần 2)
        if (has_out_2 or (has_out and not is_active_rebound)) and valid_area:
            effective_out_time = outb_t_2 if has_out_2 else outb_t
            op_date_outb = get_op_date(effective_out_time)
            if op_date_outb in (today, yesterday):
                ko = (zone, area_id, station, op_date_outb)
                if ko not in out_group:
                    out_group[ko] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
                out_group[ko]['volume']    += 1
                out_group[ko]['weight_kg'] += wt_kg

        # 3. backlog group — đơn ĐANG TỒN KHO đã từng Inbound (Lần 1 hoặc Rebound Lần 2)
        if is_currently_at_hub and (has_in or is_reb) and valid_area:
            kb = (zone, area_id, station)
            if kb not in backlog_group:
                backlog_group[kb] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            backlog_group[kb]['volume']    += 1
            backlog_group[kb]['weight_kg'] += wt_kg

        # 4. inbound group — nguồn dữ liệu cho inbound.json
        op_date_inb  = get_op_date(inb_t)  if inb_t  else ''
        op_date_fc   = get_op_date(cr_t)   if cr_t   else ''
        op_date_pick = get_op_date(pk_t)   if pk_t   else ''
        op_date_arr  = get_op_date(arr_t)  if arr_t  else ''

        final_op_date_inb = op_inb_2 if (is_reb and op_inb_2) else (op_date_inb if inb_t else '')
        final_inb_hour    = inb_t_2[11:16] if (is_reb and len(inb_t_2) >= 16) else (inb_t[11:16] if len(inb_t) >= 16 else '')

        # Mốc chuẩn để đưa đơn vào cửa sổ rolling 2 ngày của inbound.json:
        #   - Đơn đã Inbound/Rebound → dùng final_op_date_inb
        #   - Đơn đã Arrival → dùng op_date_arr
        #   - Đơn Rớt (DROP_TYPE_TODAY)     → dùng today
        #   - Đơn Rớt (DROP_TYPE_YESTERDAY) → dùng yesterday (đảm bảo không bị mất đơn rớt các ngày trước)
        if has_in or is_reb:
            ref_date = final_op_date_inb
        elif has_arr:
            ref_date = op_date_arr
        elif is_rot:
            ref_date = today if drop_type == DROP_TYPE_TODAY else yesterday
        else:
            ref_date = op_date_fc

        if ref_date in (today, yesterday):
            in_status = ('Inbound'      if (has_in or is_reb) else
                         'Transporting' if has_arr             else
                         'Pickup Done'  if has_pick            else 'Created')

            # 🎯 TỐI ƯU HOÁ GOM NHÓM AGGREGATE (PRE-AGGREGATION OLAP PIVOT):
            # 1. Đơn đã 'Inbound': UI chỉ lọc theo op_date_inbound & final_inb_hour. Các mốc tạo/pickup cũ được nén lại.
            # 2. Đơn chưa 'Inbound' (Created, Pickup Done, Transporting): bucket mốc thời gian theo khung GIỜ (HH:00:00)
            #    thay vì PHÚT (:16) vì UI chỉ dùng getHourFromTimestamp() để vẽ biểu đồ xu hướng theo giờ.
            fc_op = op_date_fc
            pk_op = op_date_pick
            ar_op = op_date_arr
            fc_hr = cr_t[:13] + ':00:00'  if len(cr_t)  >= 13 else ''
            pk_hr = pk_t[:13] + ':00:00'  if len(pk_t)  >= 13 else ''
            ar_hr = arr_t[:13] + ':00:00' if len(arr_t) >= 13 else ''

            key_ib = (
                station, pk_st_raw or 'BN HUB', in_status,
                final_op_date_inb, fc_op, pk_op, ar_op,
                final_inb_hour, fc_hr, pk_hr, ar_hr,
                drop_type, trip, transp_t, transpd_t, is_reb
            )
            if key_ib not in inbound_group:
                inbound_group[key_ib] = {'volume': 0, 'weight_kg': 0.0, 'return_count': ret_cnt}
            inbound_group[key_ib]['volume']    += 1
            inbound_group[key_ib]['weight_kg'] += wt_kg

        # ── Cờ Rớt (Chuẩn Logic Người Dùng):
        # 1. Rớt Hôm Nay   : Đơn CREATED hôm nay (op_cr == today) chưa Inbound & chưa Outbound
        # 2. Rớt Hôm Trước : Đơn CREATED/PICKUP trước hôm nay (< today), ĐÃ PICKUP/ARRIVED nhưng CHƯA INBOUND & CHƯA OUTBOUND
        if not has_in and not has_out and not is_reb and not is_canceled:
            op_cr = get_op_date(cr_t)
            op_pk = get_op_date(pk_t)
            
            if op_cr == today:
                rot_hom_nay += 1
            elif (has_pk or has_arr) and ((op_pk and op_pk < today) or (op_cr and op_cr < today)):
                rot_hom_truoc += 1

        # arrival
        if arr_t:
            op_d   = get_op_date(arr_t)
            scan_h = arr_t[:13] + ":00" if len(arr_t) >= 13 else arr_t
            ka     = (op_d, station, scan_h)
            if ka not in arr_group:
                arr_group[ka] = {'total': 0, 'at_hub': 0, 'not_hub': 0, 'last_scan_time': arr_t}
            arr_group[ka]['total'] += 1
            arr_group[ka]['at_hub' if (has_in or is_reb) else 'not_hub'] += 1
            if arr_t > arr_group[ka]['last_scan_time']:
                arr_group[ka]['last_scan_time'] = arr_t

        # heatmap — inbound hôm nay
        effective_inb_h = final_inb_hour[:2] + ":00" if len(final_inb_hour) >= 2 else ""
        if (inb_t or is_reb) and final_op_date_inb == today and effective_inb_h:
            if effective_inb_h in hourly:
                hourly[effective_inb_h] += 1

    # ── 4. Build JSON payloads ────────────────────────────────────

    inventory_json = [
        {"zone": z, "area_id": a, "station_name": s, "status": stt,
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000, 3),
         "capacity": v['capacity'], "op_date": today}
        for (z, a, s, stt), v in inv_group.items()
    ]

    outbound_json = [
        {"zone": z, "area_id": a, "station_name": s,
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000, 3),
         "capacity": v['capacity'], "op_date": op_d}
        for (z, a, s, op_d), v in out_group.items()
    ]

    backlog_json = [
        {"zone": z, "area_id": a, "station_name": s,
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000, 3),
         "capacity": v['capacity'], "op_date": today}
        for (z, a, s), v in backlog_group.items()
    ]

    inbound_json = [
        {"station_name": st, "pickup_station": pk_st, "status": status,
         "volume": stats['volume'], "weight_ton": round(stats['weight_kg'] / 1000.0, 6),
         "op_date_inbound": in_op, "op_date_forecast": fc_op,
         "op_date_pickup": pk_op, "op_date_arrival": ar_op,
         "inbound_hour": in_hr, "forecast_time": fc_hr,
         "pickup_time": pk_hr, "arrival_time": ar_hr,
         "drop_type": drop_t, "trip_code": tc,
         "transporing_time": tr_t, "transported_time": trd_t,
         "is_rebound": is_reb, "return_count": stats['return_count'],
         "is_north": (st.strip().upper().startswith('HN ') or st.strip().upper().startswith('HD ') or st.strip().upper().startswith('HY ')),
         "region": 'north' if (st.strip().upper().startswith('HN ') or st.strip().upper().startswith('HD ') or st.strip().upper().startswith('HY ')) else 'south'}
        for (st, pk_st, status, in_op, fc_op, pk_op, ar_op,
             in_hr, fc_hr, pk_hr, ar_hr,
             drop_t, tc, tr_t, trd_t, is_reb), stats in inbound_group.items()
    ]

    arrival_json = [
        {"op_date": op_d, "station_name": st, "scan_hour": hr,
         "total_orders": s['total'], "at_hub": s['at_hub'],
         "not_hub": s['not_hub'], "last_scan_time": s['last_scan_time']}
        for (op_d, st, hr), s in arr_group.items()
    ]

    # hub_inventory_pivot — mỗi station 1 dòng (tổng mọi status)
    pivot_map = {}
    for (z, a, s, _), v in inv_group.items():
        k = (z, a, s)
        if k not in pivot_map:
            pivot_map[k] = {'volume': 0, 'weight_kg': 0.0, 'capacity': v['capacity']}
        pivot_map[k]['volume']    += v['volume']
        pivot_map[k]['weight_kg'] += v['weight_kg']

    hub_pivot_json = [
        {"zone": z, "area_id": a, "station_name": s,
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000, 3),
         "capacity": v['capacity'],
         "utilization_pct": round((v['volume'] / v['capacity']) * 100, 1) if v['capacity'] else 0,
         "op_date": today}
        for (z, a, s), v in pivot_map.items()
    ]

    now_display = now_vn.strftime("%H:%M:%S %d/%m/%Y")
    # Tổng Inbound thực tế trong ca hôm nay (từ heatmap hourly)
    total_inbound_today = sum(
        v for h, v in hourly.items()
        if h >= '06:00'  # từ 06:00 sáng (đầu ca vận hành)
    )
    last_update_obj = {
        "last_update":           now_display,
        "active_date":           today,
        "yesterday":             yesterday,
        "total_records":         len(df),
        "total_inbound_today":   total_inbound_today,
        "total_backlog":         sum(v['volume'] for v in backlog_group.values()),
        "total_inventory":       sum(v['volume'] for v in inv_group.values()),
        # ── Cờ Rớt (Nguyên tắc 6): Inbound Baseline cố định 6AM vs Layout Volume live ──
        "rot_hom_truoc":         rot_hom_truoc_baseline if rot_hom_truoc_baseline > 0 else rot_hom_truoc,
        "rot_hom_truoc_live":    rot_hom_truoc,
        "rot_hom_nay":           rot_hom_nay,
        "sync_success":          True,
    }
    print(f"   📊 Cờ Rớt: Rớt hôm trước (Baseline 6AM)={last_update_obj['rot_hom_truoc']:,} | Live={rot_hom_truoc:,} | Rớt hôm nay={rot_hom_nay:,}")

    # ── 5. Validate & Write dispatch JSONs ────────────────────────
    print(f"\n📤 Validating Data Contract & Writing JSON files → {DATA_DIR}")
    validate_payload_contract(inbound_json, "inbound.json / latest.json.gz")
    validate_payload_contract(inventory_json, "inventory.json")
    write_json("inventory.json",          inventory_json)
    write_json("outbound.json",           outbound_json)
    write_json("backlog.json",            backlog_json)
    write_json("inbound.json",            inbound_json)
    write_json("arrival.json",            arrival_json)
    write_json("heatmap.json",            hourly)
    write_json("hub_inventory_pivot.json",hub_pivot_json)
    write_json("last_update.json",        last_update_obj)

    # Gzip inbound
    raw_bytes = json.dumps(inbound_json, ensure_ascii=False).encode('utf-8')
    gz_path   = os.path.join(DATA_DIR, "latest.json.gz")
    with gzip.open(gz_path, 'wb') as gz:
        gz.write(raw_bytes)
    print(f"   ✅ {'latest.json.gz':<42} {os.path.getsize(gz_path)//1024:>6} KB  |  {len(inbound_json):,} records")

    # ── 6. JFS API — Linehaul & Truck ETA ────────────────────────
    linehaul_obj  = {"generated_at": now_sys, "total_trucks": 0, "trucks": []}
    truck_eta_obj = {"generated_at": now_sys, "total_trucks_en_route": 0, "trucks": []}

    if _HAS_PIPELINE:
        print(f"\n🌐 Fetching JFS API (pipeline_unified_v6)...")
        try:
            session_lh  = build_session()
            session_arr = build_session()
            tkn_main = TokenManager(session_lh,  ACCOUNT,     PASSWORD,     label='main')
            tkn_arr  = TokenManager(session_arr, ARR_ACCOUNT, ARR_PASSWORD, label='arr')

            # Login song song
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as ex:
                fa = ex.submit(tkn_main.get_token)
                fb = ex.submit(tkn_arr.get_token)
                fa.result(); fb.result()

            # Linehaul + Shuttle song song
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_lh  = ex.submit(fetch_linehaul_json, session_lh,  tkn_main)
                f_eta = ex.submit(fetch_truck_eta_json, session_arr, tkn_arr)
                linehaul_obj  = f_lh.result()
                truck_eta_obj = f_eta.result()

        except Exception as e:
            print(f"   ⚠️  JFS API error: {e}")
    else:
        print("   ⚠️  JFS API skipped (pipeline_unified_v6 not available)")

    write_json("linehaul.json",  linehaul_obj)
    write_json("truck_eta.json", truck_eta_obj)

    # ── 7. Done ───────────────────────────────────────────────────
    elapsed = _time.time() - t0
    print(f"\n🏁 sync_postgre completed in {elapsed:.1f}s")
    print(f"   inventory={len(inventory_json):,}  outbound={len(outbound_json):,}  "
          f"backlog={len(backlog_json):,}  inbound={len(inbound_json):,}  "
          f"arrival={len(arrival_json):,}")
    print("=" * 60)

    # ── Phase 3: Git push lên GitHub ───────────────────────────
    git_push(BASE_DIR, now_sys)


def git_push(repo_dir: str, timestamp: str) -> None:
    """
    Phase 3: Tự động git add data/ src/ -> commit -> push origin main.
    Kông dừng pipeline nếu push thất bại, chỉ log lỗi.
    """
    print("\n🚀 Phase 3: Git push → GitHub...")
    try:
        # 1. git add CHI 8 file rolling (KHONG add data/history/ — write-once)
        ROLLING_FILES = [
            "data/inbound.json", "data/inventory.json", "data/outbound.json",
            "data/backlog.json", "data/last_update.json", "data/heatmap.json",
            "data/truck_eta.json", "data/linehaul.json", "data/arrival.json",
            "data/hub_inventory_pivot.json", "data/latest.json.gz",
            "src/", "backend_sync/",
        ]
        add = subprocess.run(
            ["git", "add"] + ROLLING_FILES,
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if add.returncode != 0:
            print(f"   ⚠️  git add failed: {add.stderr.strip()}")
            return

        # 2. Kiểm tra có gì thay đổi không
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
        if not status.stdout.strip():
            print("   ℹ️  Không có thay đổi mới — bỏ qua commit")
            return

        # 3. git commit
        msg = f"chore(data): auto-sync {timestamp}"
        commit = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if commit.returncode != 0:
            print(f"   ⚠️  git commit failed: {commit.stderr.strip()}")
            return
        print(f"   ✅ git commit: {msg}")

        # 4. git push
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=repo_dir, capture_output=True, text=True, timeout=60
        )
        if push.returncode != 0:
            print(f"   ❌ git push failed: {push.stderr.strip()}")
        else:
            print(f"   ✅ git push origin main — Dashboard đã cập nhật!")
            if push.stdout.strip():
                print(f"      {push.stdout.strip()}")

    except subprocess.TimeoutExpired:
        print("   ❌ Git operation timeout (>60s)")
    except FileNotFoundError:
        print("   ❌ `git` không tìm thấy trong PATH")
    except Exception as e:
        print(f"   ❌ Git push error: {e}")


if __name__ == '__main__':
    sync_postgre_to_dashboard()
