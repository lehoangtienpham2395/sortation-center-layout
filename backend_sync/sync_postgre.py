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
PG_PASS   = os.environ.get("PGPASSWORD", 'Tien@giang0203')
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
# HELPERS & UNIFIED OPERATING DATE CONTRACT (6:00 AM BOUNDARY)
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

tz_vn     = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn    = datetime.datetime.now(tz_vn)
now_sys   = now_vn.strftime("%Y-%m-%d %H:%M:%S")

# UNIFIED OPERATING DATE CONTRACT: today & yesterday follow exact 6:00 AM cycle
today     = get_op_date(now_sys)
yesterday = (datetime.datetime.strptime(today, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
tomorrow  = (datetime.datetime.strptime(today, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

start_str = (now_vn - datetime.timedelta(days=15)).strftime("%Y-%m-%d 00:00:00")
end_str   = now_vn.strftime("%Y-%m-%d %H:%M:%S")
end_plus1 = (now_vn + datetime.timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")


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
    
    if any(kw in st_lower for kw in ['đã hủy', 'cancelled', 'canceled', 'hủy', 'da huy']):
        return 'Đã hủy'
    if any(kw in st_lower for kw in ['đã xuất kho', 'outbound', 'outbound_done', 'đã xuất khỏi hub', 'đã rời hub']):
        return 'Outbound'
    if any(kw in st_lower for kw in ['đã nhập kho', 'inbound', 'inbound_done', 'đang trên bãi', 'at_hub']):
        return 'Inbound'
    if any(kw in st_lower for kw in ['đang vận chuyển', 'transporting', 'in_transit', 'chưa đến hub', 'arrival']):
        return 'Transporting'
    if any(kw in st_lower for kw in ['đã lấy hàng', 'pickup done', 'pickup_done', 'picked_up']):
        return 'Pickup Done'
    if any(kw in st_lower for kw in ['điều phối', 'tạo mới', 'chưa lấy', 'thất bại', 'created']):
        return 'Created'
    
    return 'Created'



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


def save_and_get_daily_snapshots(conn, today_date_str: str, rot_hom_truoc_val: int,
                                   rot_hom_nay_val: int, rot_ton_dong_val: int,
                                   lookback_days: int = 60) -> dict:
    """
    Tự động chốt số Forecast theo TỪNG NGÀY VẬN HÀNH — KHÔNG cần hardcode tay
    bất kỳ ngày nào trong source code (đây là nguyên nhân gốc của bug "chốt rồi
    vẫn tăng": trước đây phải tay gõ từng ngày vào dict, ngày nào quên gõ thì
    ngày đó không bao giờ được chốt, cứ tính live mãi mãi).

    Cơ chế: mỗi lần sync (30 phút/lần) chỉ UPSERT đúng 1 dòng của `today_date_str`
    với số liệu LIVE mới nhất. Vì KHÔNG dòng nào khác bị đụng tới, nên ngay khi
    một ngày không còn là "hôm nay" nữa (đã sang ngày mới), dòng của ngày đó tự
    động đứng yên vĩnh viễn — tự nhiên trở thành "đã chốt" mà không cần bất kỳ
    thao tác thủ công/hardcode nào. Áp dụng tự động cho MỌI ngày, kể cả các ngày
    trong tương lai xa mà không ai từng biết tới.
    """
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS enriched.daily_kpi_snapshot (
                op_date       DATE PRIMARY KEY,
                rot_hom_truoc INT NOT NULL DEFAULT 0,
                rot_hom_nay   INT NOT NULL DEFAULT 0,
                rot_ton_dong  INT NOT NULL DEFAULT 0,
                updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Chỉ UPSERT đúng dòng của HÔM NAY. Các ngày khác (đã kết thúc) không
        # nằm trong câu lệnh này nên không bao giờ bị ghi đè nữa.
        cur.execute("""
            INSERT INTO enriched.daily_kpi_snapshot (op_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (op_date) DO UPDATE SET
                rot_hom_truoc = EXCLUDED.rot_hom_truoc,
                rot_hom_nay   = EXCLUDED.rot_hom_nay,
                rot_ton_dong  = EXCLUDED.rot_ton_dong,
                updated_at    = CURRENT_TIMESTAMP;
        """, (today_date_str, rot_hom_truoc_val, rot_hom_nay_val, rot_ton_dong_val))
        conn.commit()

        cur.execute("""
            SELECT op_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong
            FROM enriched.daily_kpi_snapshot
            WHERE op_date >= %s::date - (%s || ' days')::interval
            ORDER BY op_date;
        """, (today_date_str, lookback_days))
        rows = cur.fetchall()
        cur.close()

        snapshots = {}
        for op_date_val, rht, rhn, rtd in rows:
            date_str = op_date_val.strftime('%Y-%m-%d')
            snapshots[date_str] = {
                "rot_hom_truoc": int(rht or 0),
                "rot_hom_nay":   int(rhn or 0),
                "rot_ton_dong":  int(rtd or 0),
                "is_frozen":     date_str != today_date_str,
            }
        print(f"   📌 Daily snapshot: tự động chốt/đọc {len(snapshots)} ngày (không hardcode) — hôm nay '{today_date_str}' vẫn live, các ngày khác đã khoá cố định.")
        return snapshots
    except Exception as e:
        print(f"   ⚠️  Không thể lưu/đọc daily_kpi_snapshot: {e}")
        return {}


def get_or_create_daily_baseline(conn, today_date_str: str) -> int:
    """
    Tạo và đọc baseline rot_hom_truoc tại 06:00 AM mỗi ngày trong PostgreSQL.
    Bảng: enriched.daily_baseline_snapshot

    ⚠️ QUAN TRỌNG: hàm này PHẢI chỉ tính COUNT(*) và ghi 1 LẦN DUY NHẤT cho mỗi
    op_date. Các lần gọi sau (mỗi 30 phút, suốt cả ngày) chỉ được ĐỌC LẠI giá trị
    đã lưu, KHÔNG được tính lại/ghi đè — nếu không baseline sẽ "trôi" theo mỗi
    lần sync thay vì đứng yên như tên hàm mô tả (đây chính là bug đã gặp: số liệu
    tưởng đã chốt nhưng vẫn tăng đều mỗi lần đồng bộ).
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

        # BƯỚC 1: Đọc trước — nếu op_date này ĐÃ có baseline rồi thì trả về ngay,
        # KHÔNG tính lại, KHÔNG ghi đè.
        cur.execute("""
            SELECT rot_hom_truoc_count FROM enriched.daily_baseline_snapshot
            WHERE op_date = %s::date;
        """, (today_date_str,))
        existing = cur.fetchone()
        if existing is not None:
            cur.close()
            print(f"   📌 Baseline Rớt Hôm Trước (ĐÃ CHỐT sẵn cho ngày {today_date_str}, đọc lại — không tính lại): {existing[0]:,} đơn")
            return existing[0]

        # BƯỚC 2: Chưa có baseline cho ngày này (lần sync đầu tiên sau 06:00 AM)
        # → tính 1 lần duy nhất rồi ghi cố định.
        yesterday_date_str = (datetime.datetime.strptime(today_date_str, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        cur.execute("""
            SELECT COUNT(*) FROM enriched.dispatch_enriched
            WHERE (inbound_scandate IS NULL)
              AND (outbound_scandate IS NULL)
              AND (next_station IS NULL OR next_station <> 'Đã hủy')
              AND (status_sys IS NULL OR status_sys <> 'Đã hủy')
              AND (is_rebound IS NULL OR is_rebound = 0)
              AND COALESCE(op_date_pickup::text, operation_date_created::text) = %s;
        """, (yesterday_date_str,))
        calc_val = cur.fetchone()[0] or 0

        # ON CONFLICT DO NOTHING: đề phòng race-condition nếu 2 tiến trình sync
        # cùng chạy đúng lúc giao ca — chỉ bản ghi đầu tiên được giữ, không ai
        # được phép ghi đè sau đó.
        cur.execute("""
            INSERT INTO enriched.daily_baseline_snapshot (op_date, rot_hom_truoc_count)
            VALUES (%s, %s)
            ON CONFLICT (op_date) DO NOTHING
            RETURNING rot_hom_truoc_count;
        """, (today_date_str, calc_val))
        row = cur.fetchone()
        conn.commit()

        if row is not None:
            final_val = row[0]
            print(f"   📌 Baseline Rớt Hôm Trước (CHỐT MỚI lúc {today_date_str} 06:00 AM, ĐÃ PICKUP, CHƯA INBOUND): {final_val:,} đơn")
        else:
            # Trường hợp cực hiếm: 1 process khác vừa insert xong trước ta 1 nhịp -> đọc lại giá trị họ đã chốt
            cur.execute("""
                SELECT rot_hom_truoc_count FROM enriched.daily_baseline_snapshot
                WHERE op_date = %s::date;
            """, (today_date_str,))
            final_val = (cur.fetchone() or [calc_val])[0]
            print(f"   📌 Baseline Rớt Hôm Trước (process khác vừa chốt trước, đọc lại cho ngày {today_date_str}): {final_val:,} đơn")

        cur.close()
        return final_val
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
    passwords = [PG_PASS, 'Tien@giang0203', 'Tien@giang0203', 'postgres']
    for pwd in passwords:
        try:
            conn = psycopg2.connect(
                dbname=PG_DBNAME, user=PG_USER, password=pwd,
                host=PG_HOST, port=PG_PORT, connect_timeout=15,
                options='-c statement_timeout=180000'
            )
            if conn: return conn
        except Exception:
            continue
    raise Exception("Could not connect to PostgreSQL logistics_db with any known password.")


def get_sa_engine():
    """SQLAlchemy engine for pd.read_sql (tránh UserWarning DBAPI2)."""
    try:
        from sqlalchemy import create_engine
        passwords = [PG_PASS, 'Tien@giang0203', 'Tien@giang0203', 'postgres']
        for pwd in passwords:
            try:
                engine = create_engine(
                    f"postgresql+psycopg2://{PG_USER}:{pwd}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}",
                    connect_args={'connect_timeout': 15, 'options': '-c statement_timeout=30000'},
                    pool_pre_ping=True,
                )
                with engine.connect() as conn:
                    pass
                return engine
            except Exception:
                continue
        return None
    except ImportError:
        return None


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
                ROUND(SUM(orders_weight)::numeric, 2) as wt_kg,
                MAX(arrival_scandate) as max_arr,
                MAX(transporing_time) as max_transp
            FROM enriched.dispatch_enriched
            WHERE flag_inbound = 0 
              AND (flag_arrival = 1 OR flag_pickup = 1)
              AND (is_completed = FALSE OR is_active = 1)
              AND UPPER(COALESCE(NULLIF(TRIM(pickup_station), ''), '')) NOT IN ('BN HUB', 'BNI001H')
            GROUP BY send_net, trip_c
            HAVING COUNT(*) >= 5
            ORDER BY vol DESC;
        """)
        rows = cur.fetchall()
        conn.close()

        # Lấy bảng mapping Station_2 -> ETA từ valid.csv
        VALID_ETA_MAP = {}
        try:
            v_paths = [
                r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv',
                r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid.csv',
                os.path.join(BASE_DIR, 'valid.csv')
            ]
            for vp in v_paths:
                if os.path.exists(vp):
                    _dfv = pd.read_csv(vp, encoding='utf-8-sig')
                    if 'Station_2' in _dfv.columns and 'ETA' in _dfv.columns:
                        for _, _r in _dfv.iterrows():
                            _s2 = str(_r.get('Station_2', '')).strip().upper()
                            _ev = _r.get('ETA')
                            if _s2 and pd.notna(_ev):
                                try:
                                    VALID_ETA_MAP[_s2] = float(_ev)
                                except Exception:
                                    pass
                        break
        except Exception:
            pass

        def compute_truck_eta(send_st: str, transp_t: str, arr_t: str = '') -> str:
            # Rule 1: Các chuyến xe chưa có transporting -> bỏ qua hiển thị, trả về ""
            if not transp_t or len(str(transp_t).strip()) < 10:
                return ""
            try:
                ts_str = str(transp_t).strip()[:19]
                fmt = '%Y-%m-%d %H:%M:%S' if len(ts_str) >= 19 else ('%Y-%m-%d %H:%M' if len(ts_str) >= 16 else '%Y-%m-%d')
                dep_dt = datetime.datetime.strptime(ts_str, fmt)
                st_u = (send_st or '').strip().upper()

                # Rule 2 & 3: Mapping Station_2 -> Cột ETA từ valid.csv
                hours_add = VALID_ETA_MAP.get(st_u)
                if hours_add is None:
                    if st_u.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')):
                        hours_add = 36.0
                    elif st_u.startswith(('CT ', 'KG ', 'AG ', 'BL ', 'CM ', 'ST ', 'TV ', 'VL ', 'TG ', 'DT ', 'LA ')):
                        hours_add = 4.0
                    elif st_u.startswith(('BD ', 'DN ', 'TN ', 'VT ')):
                        hours_add = 2.0
                    else:
                        hours_add = 1.5

                return (dep_dt + datetime.timedelta(hours=hours_add)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(transp_t)

        for r in rows:
            send_st, arr_st, trip, vol, wt_kg, max_arr, max_transp = r
            ref_dep = str(max_transp or '')[:16]
            calc_eta = compute_truck_eta(send_st, max_transp, max_arr)[:16]
            op_d = get_op_date(ref_dep or calc_eta) if (ref_dep or calc_eta) else today

            if op_d in (today, yesterday):
                key = (send_st, trip)
                seen_keys.add(key)
                calc_wt_ton = round(float(wt_kg) / 1000.0, 3)
                trucks.append({
                    "send_network":     send_st,
                    "arrive_network":   arr_st,
                    "trip_code":        trip,
                    "orders_count":     int(vol),
                    "weight_kg":        float(wt_kg),
                    "weight_ton":       calc_wt_ton,
                    "planned_departure":ref_dep,
                    "planned_arrival":  calc_eta,
                    "actual_departure": str(max_transp or '')[:16],
                    "actual_arrival":   str(max_arr or '')[:16],
                    "eta":              calc_eta,
                    "rank":             "Linehaul" if (send_st or '').strip().upper().startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) else "Shuttle",
                    "status":           "arrived" if max_arr else "in_transit",
                    "op_date":          op_d,
                })
    except Exception as e:
        print(f"   ⚠️ PostgreSQL truck_eta aggregation error: {e}")

    # ── 2. JFS API: Bổ sung các chuyến Linehaul & Shuttle thực tế từ TMS ──
    try:
        start_4d = (datetime.datetime.now(tz_vn) - datetime.timedelta(days=4)).strftime('%Y-%m-%d 00:00:00')
        lh_recs = pull_linehaul_consol(session, token_mgr, start_4d, end_plus1)
        for row in lh_recs:
            arr_net  = str(row.get('arriveNetworkName') or row.get('endName') or '').strip()
            send_net = str(row.get('sendNetworkName') or row.get('startName') or '').strip()
            trip     = str(row.get('shipmentNo') or row.get('taskNo') or '').strip().upper()
            orders_cnt = int(row.get('loadscanwaybillnum') or row.get('waybillNum') or 0)

            # 🎯 CHỈ LẤY CÁC XE ĐANG CHẠY ĐẾN HCM HUB (INBOUND TRUCK ETA)
            # BỎ QUA các xe xuất phát từ HCM HUB đi tỉnh (Outbound Linehaul)
            if orders_cnt <= 0 or not trip or 'HCM' in send_net.upper() or ('HCM' not in arr_net.upper() and arr_net != ''):
                continue

            key = (send_net, trip)
            if key not in seen_keys:
                seen_keys.add(key)
                p_dep = str(row.get('plannedDepartureTime') or row.get('scanTime') or '').strip()
                actual_dep = str(row.get('actualDepartureTime') or row.get('trackOutTime') or '').strip()
                actual_arr = str(row.get('actualArrivalTime') or row.get('unloadEndTime') or '').strip()
                ref_t = actual_dep or p_dep

                # 🎯 THỜI GIAN DI CHUYỂN LINEHAUL BẮC - NAM = +36 TIẾNG TỪ THỜI DIỂM KHỞI HÀNH (BN HUB)
                calc_eta = ""
                if ref_t:
                    try:
                        dep_dt = datetime.datetime.strptime(ref_t[:19], '%Y-%m-%d %H:%M:%S')
                        calc_eta = (dep_dt + datetime.timedelta(hours=36)).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        calc_eta = ref_t

                if not calc_eta:
                    calc_eta = str(row.get('predictArriveTime') or row.get('plannedArrivalTime') or '').strip()

                op_d = get_op_date(calc_eta) if calc_eta else today
                wt_kg = float(row.get('loadpackageweight') or 0)
                trucks.append({
                    "send_network":     send_net,
                    "arrive_network":   arr_net,
                    "trip_code":        trip,
                    "orders_count":     orders_cnt,
                    "weight_kg":        wt_kg,
                    "weight_ton":       round(wt_kg / 1000.0, 3),
                    "planned_departure":p_dep,
                    "planned_arrival":  calc_eta,
                    "actual_departure": actual_dep,
                    "actual_arrival":   actual_arr,
                    "eta":              calc_eta,
                    "rank":             "Linehaul",
                    "status":           "arrived" if actual_arr else ("in_transit" if actual_dep else "loading"),
                    "op_date":          op_d,
                })
    except Exception as e:
        print(f"   ⚠️ pull_linehaul_consol API call skipped/failed: {e}")

    try:
        today_start = today + ' 00:00:00'
        recs = pull_shuttle(session, token_mgr, today_start, end_plus1)
        for row in recs:
            actual_arr = str(row.get('actualArrivalTime') or '').strip()
            if actual_arr:
                continue

            orders_cnt = int(row.get('loadscanwaybillnum') or row.get('waybillNum') or 0)
            if orders_cnt <= 0:
                continue  # Bỏ qua các chuyến rỗng không có đơn

            p_dep = str(row.get('plannedDepartureTime') or row.get('createTime') or '').strip()
            actual_dep = str(row.get('actualDepartureTime') or row.get('appDepartureTime') or '').strip()
            trip = str(row.get('shipmentNo') or row.get('taskNo') or '').strip().upper()
            send_net = str(row.get('sendNetworkName') or row.get('startName') or '').strip()
            arr_net  = str(row.get('arriveNetworkName') or row.get('endName') or '').strip()

            if 'HCM' in send_net.upper():
                continue  # Bỏ qua các xe shuttle xuất phát từ HCM HUB

            key = (send_net, trip)
            if key not in seen_keys:
                seen_keys.add(key)
                ref_t = actual_dep or p_dep
                op_d = get_op_date(ref_t) if ref_t else today
                if op_d == today:
                    wt_kg = float(row.get('loadpackageweight') or 0)
                    shuttle_eta = compute_truck_eta(send_net, actual_dep or p_dep) or str(row.get('estimateArrivalTime') or '').strip()
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
                        "eta":              shuttle_eta,
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
        st_col   = next((c for c in ['Station_2', 'Station_1', 'Bưu cục'] if c in df_v.columns), None)
        zone_col = next((c for c in ['Zone', 'Hubcode'] if c in df_v.columns), None)

        for _, r_v in df_v.iterrows():
            st2 = str(r_v.get('Station_2') or r_v.get('Station_1') or '').strip()
            ar  = str(r_v.get('area') or '').strip()
            zn  = str(r_v.get('Zone') or '3').strip()
            st1 = str(r_v.get('Station_1') or '').strip().upper()
            if st1:
                dict_station[st1] = st2
                dict_area[st1]    = ar
                dict_zone[st1]    = zn


            sc = str(r_v.get('sortcode') or '').strip().upper()

            if sc:
                dict_station[sc] = st2
                dict_area[sc]    = ar
                dict_zone[sc]    = zn
                if len(sc) >= 6:
                    dict_station[sc[:6]] = st2
                    dict_area[sc[:6]]    = ar
                    dict_zone[sc[:6]]    = zn

            hub = str(r_v.get('Hubcode') or '').strip().upper()
            if hub and hub not in ('SR0001', 'SR0002'):
                dict_station[hub] = st2
                dict_area[hub]    = ar
                dict_zone[hub]    = zn
                if len(hub) >= 6:
                    dict_station[hub[:6]] = st2
                    dict_area[hub[:6]]    = ar
                    dict_zone[hub[:6]]    = zn

        print(f"   valid.csv : {len(dict_area):,} sortcode+Hubcode mappings (Master Google Sheet Config)")
    else:
        print(f"   ⚠️  valid.csv not found — zone/area mapping empty")


    # ── Phase 1: JFS API → PostgreSQL (import trực tiếp pipeline_unified_v6.py) ──
    if '--skip-jfs' in sys.argv or '--fast' in sys.argv or '-f' in sys.argv:
        print("\n⏩ Skipping Phase 1 (JFS API fetch) — Running Fast Phase 2 & JSON export directly from PostgreSQL...")
    else:
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
        WHERE 
            -- POOL 1: TẤT CẢ các đơn ĐANG HOẠT ĐỘNG / TỒN KHO / ĐANG CHẠY
            (is_active = 1 OR is_completed = FALSE)

            -- POOL 2: Các đơn thuộc Ngày vận hành Hôm nay & Hôm qua (Cửa sổ 2 ngày ca vận hành)
            OR COALESCE(op_date_pickup::date, operation_date_created::date) >= %(op_yesterday)s::date
        ORDER BY operation_date_created DESC, created_time DESC
    """
    params = {'op_yesterday': yesterday}
    try:
        sa_engine = get_sa_engine()
        if sa_engine:
            df = pd.read_sql(query, sa_engine, params=params)
            sa_engine.dispose()
            print("   🟢 Connected to PostgreSQL (SQLAlchemy)")
        else:
            # Fallback nếu sqlalchemy chưa cài
            import warnings
            conn = get_pg_conn()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                df = pd.read_sql(query, conn, params=params)
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
    yest_rows  = len(df[df['operation_date_created'].astype(str).str[:10] == yesterday])
    print(f"   📦 {total_rows:,} records từ PostgreSQL (Live & Active 2 ngày)")
    print(f"   📅 Ngày vận hành hôm nay ({today}): {today_rows:,} đơn")
    print(f"   📅 Ngày hôm qua ({yesterday})       : {yest_rows:,} đơn")

    # ── 3. Aggregate ──────────────────────────────────────────────
    inv_group     = {}   # (zone, area_id, station_name, status) → {volume, weight_kg, capacity}
    out_group     = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    backlog_group = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    inbound_group = {}   # 14-tuple key                          → {volume, weight_kg}
    arr_group     = {}   # (op_date, station_name, scan_hour)    → {total, at_hub, not_hub, last_scan_time}
    hourly        = {f"{h:02d}:00": 0 for h in range(24)}
    try:
        today_dt = datetime.datetime.strptime(today, '%Y-%m-%d')
        yesterday_str = (today_dt - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    except Exception:
        yesterday_str = ''

    # ── Cờ Rớt đơn (Nguyên tắc 6) ────────────────────────────────
    # rot_hom_truoc_baseline: GIỮ LẠI biến này để tương thích ngược (dùng ở vài
    # chỗ khác trong script), nhưng việc CHỐT thật sự giờ nằm ở
    # save_and_get_daily_snapshots() gọi bên dưới, sau khi rot_hom_truoc/nay/ton_dong
    # đã được tính xong từ vòng lặp chính.
    rot_hom_truoc_baseline = 0
    try:
        conn_b = get_pg_conn()
        rot_hom_truoc_baseline = get_or_create_daily_baseline(conn_b, today)
        conn_b.close()
    except Exception as _eb:
        print(f"   ⚠️ Baseline query error: {_eb}")

    rot_hom_truoc = 0   # Pickup hôm trước, chưa về HUB → live dynamic tracking cho Layout Volume
    rot_hom_nay   = 0   # Pickup hôm nay, chưa về HUB  → đang trên đường
    rot_ton_dong  = 0   # Tồn đọng lâu ngày
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

        pk_st_upper = pk_st_raw.strip().upper()
        is_north_record = (
            target_st_upper == 'BN HUB' or
            target_st_upper.startswith('HN ') or
            target_st_upper.startswith('HD ') or
            target_st_upper.startswith('HY ') or
            dict_area.get(sc) == 'A06'
        )


        if is_north_record:
            area_id = 'A06'
            station = 'BN HUB'
            zone    = '1'
        elif target_st_upper in OFFICIAL_STATION_TO_AREA:
            area_id = OFFICIAL_STATION_TO_AREA[target_st_upper]
            station = OFFICIAL_LAYOUT_MAP[area_id][0]
            zone    = OFFICIAL_LAYOUT_MAP[area_id][1]
        elif sc and dict_area.get(sc):
            area_id = dict_area.get(sc)
            if area_id in OFFICIAL_LAYOUT_MAP:
                station = OFFICIAL_LAYOUT_MAP[area_id][0]
                zone    = OFFICIAL_LAYOUT_MAP[area_id][1]
            else:
                station = dict_station.get(sc, target_st)
                zone    = ZONE_MAP.get(dict_zone.get(sc, '3'), '3')
        else:
            station = target_st or 'Chưa phân vùng'
            area_id = OFFICIAL_STATION_TO_AREA.get(station.upper(), 'C01')
            if area_id in OFFICIAL_LAYOUT_MAP:
                station = OFFICIAL_LAYOUT_MAP[area_id][0]
                zone    = OFFICIAL_LAYOUT_MAP[area_id][1]
            else:
                zone = '3'

        if area_id == 'A06':
            station = 'BN HUB'
            zone = '1'



        valid_area = bool(area_id)
        cap      = 1400 if area_id == 'A06' else 780
        raw_wt   = float(r.get('orders_weight') or 0)
        wt_kg    = (raw_wt / 1000.0) if raw_wt > 5000.0 else raw_wt
        cr_t     = clean_ts_str(r.get('created_time'))
        pk_t     = clean_ts_str(r.get('pickup_time'))
        pk_st    = str(r.get('pickup_station') or '').upper()
        inb_t    = clean_ts_str(r.get('inbound_scandate'))
        outb_t   = clean_ts_str(r.get('outbound_scandate'))
        arr_t    = clean_ts_str(r.get('arrival_scandate'))
        trip     = str(r.get('trip_code',           '')).strip()
        transp_t = clean_ts_str(r.get('transporing_time'))
        transpd_t= clean_ts_str(r.get('transported_time'))
        op_date  = str(r.get('operation_date_created', today))[:10] or today

        op_date_inb_eff = str(r.get('operation_date_inbound') or r.get('op_date_inbound_effective') or '')[:10]
        has_in   = bool(inb_t or op_date_inb_eff)
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
        DROP_TYPE_TODAY     = 'Rớt hôm nay'
        DROP_TYPE_YESTERDAY = 'Rớt hôm trước'
        DROP_TYPE_AGED      = 'Tồn đọng lâu ngày'

        st_sys_val = str(r.get('status_sys') or r.get('status') or '').strip()
        is_canceled = (st_sys_val == 'Đã hủy')
        pk_st = str(r.get('pickup_station') or '').strip().upper()
        next_st = str(r.get('next_station') or '').strip().upper()
        st_name = str(station or '').strip().upper()
        rk_val = str(r.get('rank') or '').strip().upper()
        rd_val = str(r.get('round') or '').strip().upper()
        is_north = (
            pk_st.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or 
            next_st.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or 
            st_name.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or 
            rk_val == 'BN HUB' or 
            'LINEHAUL' in rd_val
        )
        is_rot = (not has_in) and (not has_out) and (not is_canceled) and (not is_reb) and (not is_north)

        ref_rot_date = str(r.get('op_date_pickup') or get_op_date(cr_t) or op_date or '')[:10]
        if is_rot:
            if ref_rot_date == today:
                rot_hom_nay   += 1
                drop_type = DROP_TYPE_TODAY
            elif ref_rot_date == yesterday:
                rot_hom_truoc += 1
                drop_type = DROP_TYPE_YESTERDAY
            else:
                rot_ton_dong  += 1
                drop_type = DROP_TYPE_AGED
        else:
            drop_type = ''

        is_active_rebound = (is_reb == 1 and not has_out_2)
        is_currently_at_hub = (not has_out) or is_active_rebound
        st_sys_raw = str(r.get('status_sys', '')).strip()
        has_pk = bool(r.get('flag_pickup') or pk_t or st_sys_raw in ('Đã lấy hàng', 'Pickup Done', 'pickup_done'))

        inv_status = ('Inbound'      if is_active_rebound else
                      'Outbound'     if (has_out and not is_active_rebound) else
                      'Inbound'      if has_in  else
                      'Transporting' if has_arr else
                      'Pickup Done'  if has_pk else 'Created')

        # 🎯 1. inventory group — Đơn thuộc NGÀY VẬN HÀNH tương ứng & LOẠI BỎ 'Outbound'
        is_not_outbound = (inv_status != 'Outbound' and not has_out)
        
        if is_not_outbound and valid_area:
            ki = (zone, area_id, station, inv_status, op_date)
            if ki not in inv_group:
                inv_group[ki] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            inv_group[ki]['volume']    += 1
            inv_group[ki]['weight_kg'] += wt_kg

        # 🎯 2. outbound group — CHỈ nhận đơn CÓ MỐC THỜI GIAN XUẤT KHO THỰC TẾ (effective_out_time)
        if (has_out_2 or (has_out and not is_active_rebound)) and valid_area:
            effective_out_time = outb_t_2 if has_out_2 else outb_t
            if effective_out_time and len(effective_out_time) >= 10:
                op_date_outb = get_op_date(effective_out_time)
                if op_date_outb in (today, yesterday):
                    ko = (zone, area_id, station, op_date_outb)
                    if ko not in out_group:
                        out_group[ko] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
                    out_group[ko]['volume']    += 1
                    out_group[ko]['weight_kg'] += wt_kg

        # 🎯 3. backlog group — đơn ĐANG TỒN KHO (Tồn đọng cả ngày cũ và ngày mới)
        if is_currently_at_hub and (has_in or is_reb) and valid_area:
            kb = (zone, area_id, station, op_date)
            if kb not in backlog_group:
                backlog_group[kb] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            backlog_group[kb]['volume']    += 1
            backlog_group[kb]['weight_kg'] += wt_kg

        # 4. inbound group — nguồn dữ liệu cho inbound.json
        op_date_inb  = get_op_date(inb_t)  if inb_t  else ''
        op_date_fc   = get_op_date(cr_t)   if cr_t   else ''
        op_date_pick = get_op_date(pk_t)   if pk_t   else ''
        op_date_arr  = get_op_date(arr_t)  if arr_t  else ''
        actual_op_date_inb = op_inb_2 if (is_reb and op_inb_2) else (op_date_inb if inb_t else '')
        final_op_date_inb  = actual_op_date_inb or (op_date_arr or op_date_pick or op_date_fc or today)
        final_inb_hour     = inb_t_2[11:16] if (is_reb and len(inb_t_2) >= 16) else (inb_t[11:16] if len(inb_t) >= 16 else '')

        if has_in or is_reb:
            ref_date = final_op_date_inb or today
        elif has_arr:
            ref_date = op_date_arr or today
        elif has_pick:
            ref_date = op_date_pick or today
        else:
            ref_date = op_date_fc or today

        if ref_date in (today, yesterday):
            in_status = ('Inbound'      if (has_in or is_reb or inb_t) else
                         'Transporting' if (has_arr or arr_t or transp_t) else
                         'Pickup Done'  if (has_pick or pk_t) else 'Created')

            fc_op = op_date_fc
            pk_op = op_date_pick
            ar_op = op_date_arr
            fc_hr = cr_t[:13] + ':00:00'  if len(cr_t)  >= 13 else ''
            pk_hr = pk_t[:13] + ':00:00'  if len(pk_t)  >= 13 else ''
            ar_hr = arr_t[:13] + ':00:00' if len(arr_t) >= 13 else ''
            drop_t = drop_type
            key_ib = (
                station, pk_st_raw or 'BN HUB', in_status, ref_date, fc_op, pk_op, ar_op,
                final_inb_hour, fc_hr, pk_hr, ar_hr,
                drop_type, trip, transp_t, transpd_t, is_reb
            )
            if key_ib not in inbound_group:
                inbound_group[key_ib] = {'volume': 0, 'weight_kg': 0.0, 'return_count': ret_cnt}
            inbound_group[key_ib]['volume']    += 1
            inbound_group[key_ib]['weight_kg'] += wt_kg

        # arrival
        if arr_t:
            op_d   = get_op_date(arr_t)
            scan_h = arr_t[:13] + ":00" if len(arr_t) >= 13 else arr_t
            arr_st = (pk_st_raw or station).strip()
            ka     = (op_d, arr_st, scan_h)
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
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000.0, 6),
         "capacity": v['capacity'], "op_date": d}
        for (z, a, s, stt, d), v in inv_group.items()
    ]

    outbound_json = [
        {"zone": z, "area_id": a, "station_name": s, "status": "Outbound",
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000.0, 6),
         "capacity": v['capacity'], "op_date": op_d}
        for (z, a, s, op_d), v in out_group.items()
    ]

    backlog_json = [
        {"zone": z, "area_id": a, "station_name": s, "status": "Inbound",
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000.0, 6),
         "capacity": v['capacity'], "op_date": d}
        for (z, a, s, d), v in backlog_group.items()
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
    for (z, a, s, _, _d), v in inv_group.items():
        k = (z, a, s)
        if k not in pivot_map:
            pivot_map[k] = {'volume': 0, 'weight_kg': 0.0, 'capacity': v['capacity']}
        pivot_map[k]['volume']    += v['volume']
        pivot_map[k]['weight_kg'] += v['weight_kg']

    hub_pivot_json = [
        {"zone": z, "area_id": a, "station_name": s,
         "volume": v['volume'], "weight_ton": round(v['weight_kg'] / 1000.0, 6),
         "capacity": v['capacity'],
         "utilization_pct": round((v['volume'] / v['capacity']) * 100, 1) if v['capacity'] else 0,
         "op_date": today}
        for (z, a, s), v in pivot_map.items()
    ]

    now_display = now_vn.strftime("%H:%M:%S %d/%m/%Y")
    # Tổng Inbound thực tế trong ca hôm nay (từ heatmap 24 giờ ca vận hành 06:00 -> 05:00)
    total_inbound_today = sum(hourly.values())
    # 🎯 TỰ ĐỘNG chốt + đọc snapshot cho MỌI ngày — không hardcode bất kỳ ngày nào.
    # Đây chính là điểm sửa cho bug "chốt rồi vẫn tăng": trước đây dict này bị gõ
    # tay từng ngày, ngày nào quên gõ thì mãi mãi không được chốt.
    try:
        conn_snap = get_pg_conn()
        daily_snapshots = save_and_get_daily_snapshots(
            conn_snap, today,
            rot_hom_truoc_val=rot_hom_truoc,
            rot_hom_nay_val=rot_hom_nay,
            rot_ton_dong_val=rot_ton_dong,
        )
        conn_snap.close()
    except Exception as _es:
        print(f"   ⚠️ Daily snapshot error: {_es}")
        daily_snapshots = {
            today: {
                "rot_hom_truoc": rot_hom_truoc_baseline if rot_hom_truoc_baseline > 0 else rot_hom_truoc,
                "rot_hom_nay":   rot_hom_nay,
                "rot_ton_dong":  rot_ton_dong,
                "is_frozen":     False,
            }
        }
    last_update_obj = {
        "last_update":           now_display,
        "active_date":           today,
        "yesterday":             yesterday,
        "total_records":         len(df),
        "total_inbound_today":   total_inbound_today,
        "total_backlog":         sum(v['volume'] for v in backlog_group.values()),
        "total_inventory":       sum(v['volume'] for v in inv_group.values()),
        "rot_hom_truoc":         rot_hom_truoc_baseline if rot_hom_truoc_baseline > 0 else rot_hom_truoc,
        "rot_hom_truoc_live":    rot_hom_truoc,
        "rot_hom_nay":           rot_hom_nay,
        "daily_snapshots":       daily_snapshots,
        "contract_version":      "2.0.0",
        "sync_success":          True,
    }
    print(f"   📊 Cờ Rớt: Rớt hôm trước (Baseline 6AM)={last_update_obj['rot_hom_truoc']:,} | Live={rot_hom_truoc:,} | Rớt hôm nay={rot_hom_nay:,}")

    # ── 5. Build Micro-JSONs (Data Architecture v2.0 - Ultra Light) ──
    print(f"\n⚡ Building Micro-JSON Payloads (Data Architecture v2.0)...")
    
    def is_linehaul_item(st, pk, status):
        st_u = str(pk or st or '').strip().upper()
        return st_u.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or 'BN' in st_u

    # 5.1 Calculate status_counts first for exact 4-stage sum
    status_counts  = {'Inbound': 0, 'Transporting': 0, 'Pickup Done': 0, 'Created': 0}
    status_weights = {'Inbound': 0.0, 'Transporting': 0.0, 'Pickup Done': 0.0, 'Created': 0.0}

    for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items():
        std_status = ('Inbound' if status in ('Inbound', 'Đã nhập kho') else
                      'Transporting' if status in ('Transporting', 'Đang vận chuyển') else
                      'Pickup Done' if status in ('Pickup Done', 'Đã lấy hàng') else
                      'Created' if status in ('Created', 'Đơn mới tạo') else '')
        
        if not std_status:
            continue

        if std_status == 'Inbound':
            if in_op == today:
                status_counts['Inbound'] += stats['volume']
                status_weights['Inbound'] += stats['weight_kg'] / 1000.0
        else:
            is_match = (in_op == today) or (ar_op == today) or (pk_op == today) or (fc_op == today) or (fc_op and fc_op < today)
            if is_match:
                status_counts[std_status] += stats['volume']
                status_weights[std_status] += stats['weight_kg'] / 1000.0

    inbound_orders_status = {
        "op_date": today,
        "contract_version": "2.0.0",
        "inbound": status_counts['Inbound'],
        "transporting": status_counts['Transporting'],
        "pickup_done": status_counts['Pickup Done'],
        "created": status_counts['Created'],
        "total": sum(status_counts.values()),
        "inbound_weight": round(status_weights['Inbound'], 3),
        "transporting_weight": round(status_weights['Transporting'], 3),
        "pickup_done_weight": round(status_weights['Pickup Done'], 3),
        "created_weight": round(status_weights['Created'], 3)
    }

    # 🎯 FORECAST TOTAL MUST ALWAYS EQUAL THE SUM OF ALL 4 OPERATING STAGES (INBOUND + TRANSPORTING + PICKUP DONE + CREATED)
    fc_total_4stages = status_counts['Inbound'] + status_counts['Transporting'] + status_counts['Pickup Done'] + status_counts['Created']
    fc_total_weight  = round(status_weights['Inbound'] + status_weights['Transporting'] + status_weights['Pickup Done'] + status_weights['Created'], 3)
    
    # 🎯 100% DYNAMIC LINEHAUL CALCULATION (No hardcoded static numbers)
    fc_linehaul = sum(
        stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items()
        if (in_op == today or ar_op == today or pk_op == today or fc_op == today or (fc_op and fc_op < today))
        and is_linehaul_item(st, pk, status)
    )
    linehaul_weight_ton = round(sum(
        stats['weight_kg'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items()
        if (in_op == today or ar_op == today or pk_op == today or fc_op == today or (fc_op and fc_op < today))
        and is_linehaul_item(st, pk, status)
    ) / 1000.0, 3)

    if fc_linehaul > fc_total_4stages:
        fc_linehaul = min(fc_linehaul, int(fc_total_4stages * 0.35))
    if linehaul_weight_ton > fc_total_weight:
        linehaul_weight_ton = min(linehaul_weight_ton, round(fc_total_weight * 0.35, 3))

    fc_shuttle = max(0, fc_total_4stages - fc_linehaul)
    shuttle_weight_ton = max(0.0, round(fc_total_weight - linehaul_weight_ton, 3))
    total_inb_wt_kg = sum(stats['weight_kg'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items() if in_op == today)
    inbound_weight_ton = round(total_inb_wt_kg / 1000.0, 1) if total_inbound_today > 0 else 0.0

    inbound_kpi_summary = {
        "op_date": today,
        "contract_version": "2.0.0",
        "inbound_orders": total_inbound_today,
        "inbound_weight_ton": inbound_weight_ton,
        "forecast_total": fc_total_4stages,
        "forecast_weight_ton": fc_total_weight,
        "shuttle": fc_shuttle,
        "shuttle_weight": shuttle_weight_ton,
        "linehaul": fc_linehaul,
        "linehaul_weight": linehaul_weight_ton
    }

    # 5.2 inbound_hourly_trend.json
    hours_list = [f"{h:02d}:00" for h in (list(range(6, 24)) + list(range(0, 6)))]
    hourly_series_inbound = [hourly.get(h, 0) for h in hours_list]
    hourly_series_transporting = []
    hourly_series_pickup_done = []
    hourly_series_created = []

    for h in hours_list:
        h_prefix = h[:2]
        tr_vol = sum(stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, in_hr, fc_hr, pk_hr, ar_hr, *rest), stats in inbound_group.items() if len(ar_hr) >= 13 and ar_hr[11:13] == h_prefix and ar_op == today)
        pk_vol = sum(stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, in_hr, fc_hr, pk_hr, ar_hr, *rest), stats in inbound_group.items() if len(pk_hr) >= 13 and pk_hr[11:13] == h_prefix and pk_op == today)
        cr_vol = sum(stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, in_hr, fc_hr, pk_hr, ar_hr, *rest), stats in inbound_group.items() if len(fc_hr) >= 13 and fc_hr[11:13] == h_prefix and fc_op == today)
        hourly_series_transporting.append(tr_vol)
        hourly_series_pickup_done.append(pk_vol)
        hourly_series_created.append(cr_vol)

    inbound_hourly_trend = {
        "op_date": today,
        "contract_version": "2.0.0",
        "hours": hours_list,
        "series": {
            "inbound": hourly_series_inbound,
            "transporting": hourly_series_transporting,
            "pickup_done": hourly_series_pickup_done,
            "created": hourly_series_created
        }
    }

    # 5.3 inbound_orders_status.json
    status_counts  = {'Inbound': 0, 'Transporting': 0, 'Pickup Done': 0, 'Created': 0}
    status_weights = {'Inbound': 0.0, 'Transporting': 0.0, 'Pickup Done': 0.0, 'Created': 0.0}

    for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items():
        std_status = ('Inbound' if status in ('Inbound', 'Đã nhập kho') else
                      'Transporting' if status in ('Transporting', 'Đang vận chuyển') else
                      'Pickup Done' if status in ('Pickup Done', 'Đã lấy hàng') else
                      'Created' if status in ('Created', 'Đơn mới tạo') else '')
        
        if not std_status:
            continue

        if std_status == 'Inbound':
            if in_op == today:
                status_counts['Inbound'] += stats['volume']
                status_weights['Inbound'] += stats['weight_kg'] / 1000.0
        else:
            is_match = (in_op == today) or (ar_op == today) or (pk_op == today) or (fc_op == today) or (fc_op and fc_op < today)
            if is_match:
                status_counts[std_status] += stats['volume']
                status_weights[std_status] += stats['weight_kg'] / 1000.0

    inbound_orders_status = {
        "op_date": today,
        "contract_version": "2.0.0",
        "inbound": status_counts['Inbound'],
        "transporting": status_counts['Transporting'],
        "pickup_done": status_counts['Pickup Done'],
        "created": status_counts['Created'],
        "total": sum(status_counts.values()),
        "inbound_weight": round(status_weights['Inbound'], 3),
        "transporting_weight": round(status_weights['Transporting'], 3),
        "pickup_done_weight": round(status_weights['Pickup Done'], 3),
        "created_weight": round(status_weights['Created'], 3)
    }

    # 5.4 inbound_origin_station.json
    origin_map = {}
    for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items():
        pk_clean = (pk or st).strip()
        if not pk_clean:
            continue
        is_match = (in_op == today) or (ar_op == today) or (pk_op == today) or (fc_op == today)
        if is_match:
            if pk_clean not in origin_map:
                origin_map[pk_clean] = {'total_volume': 0, 'inbound_volume': 0, 'transporting_volume': 0, 'pickup_done_volume': 0, 'created_volume': 0, 'total_weight': 0.0, 'inbound_weight': 0.0}
            vol = stats['volume']
            wt_ton = stats['weight_kg'] / 1000.0
            origin_map[pk_clean]['total_volume'] += vol
            origin_map[pk_clean]['total_weight'] += wt_ton
            if status in ('Inbound', 'Đã nhập kho') and in_op == today:
                origin_map[pk_clean]['inbound_volume'] += vol
                origin_map[pk_clean]['inbound_weight'] += wt_ton
            elif status in ('Transporting', 'Đang vận chuyển'):
                origin_map[pk_clean]['transporting_volume'] += vol
            elif status in ('Pickup Done', 'Đã lấy hàng'):
                origin_map[pk_clean]['pickup_done_volume'] += vol
            elif status in ('Created', 'Đơn mới tạo'):
                origin_map[pk_clean]['created_volume'] += vol

    stations_list = [
        {
            "station_name": k,
            "total_volume": v['total_volume'],
            "inbound_volume": v['inbound_volume'],
            "transporting_volume": v['transporting_volume'],
            "pickup_done_volume": v['pickup_done_volume'],
            "created_volume": v['created_volume'],
            "inbound_weight_ton": round(v['inbound_weight'], 2),
            "total_weight_ton": round(v['total_weight'], 2)
        }
        for k, v in origin_map.items()
    ]
    stations_list.sort(key=lambda x: x['total_volume'], reverse=True)

    inbound_origin_station = {
        "op_date": today,
        "contract_version": "2.0.0",
        "stations": stations_list
    }

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

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as ex:
                fa = ex.submit(tkn_main.get_token)
                fb = ex.submit(tkn_arr.get_token)
                fa.result(); fb.result()

            with ThreadPoolExecutor(max_workers=2) as ex:
                f_lh  = ex.submit(fetch_linehaul_json, session_lh,  tkn_main)
                f_eta = ex.submit(fetch_truck_eta_json, session_arr, tkn_arr)
                linehaul_obj  = f_lh.result()
                truck_eta_obj = f_eta.result()

        except Exception as e:
            print(f"   ⚠️  JFS API error: {e}")
    else:
        print("   ⚠️  JFS API skipped (pipeline_unified_v6 not available)")

    inbound_truck_eta = {
        "op_date": today,
        "contract_version": "2.0.0",
        "trucks": truck_eta_obj.get("trucks", [])
    }

    # Recalculate Transporting in inbound_orders_status from Arrival dataset as instructed
    arr_trucks = truck_eta_obj.get("trucks", [])
    arr_shuttle_orders = 0
    arr_shuttle_weight = 0.0
    
    for tr in arr_trucks:
        st_name = str(tr.get("station_name") or tr.get("send_network") or "").strip().upper()
        if not st_name.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')):
            vol = int(tr.get("total_orders") or tr.get("orders_count") or tr.get("volume") or 0)
            wt = float(tr.get("weight") or tr.get("weight_ton") or 0)
            wt_ton = wt / 1000.0 if wt > 100 else wt
            arr_shuttle_orders += vol
            arr_shuttle_weight += wt_ton

    if arr_shuttle_orders > 0:
        inbound_orders_status["transporting"] = arr_shuttle_orders
        inbound_orders_status["transporting_weight"] = round(arr_shuttle_weight, 3)
        inbound_orders_status["total"] = (inbound_orders_status["inbound"] +
                                          inbound_orders_status["transporting"] +
                                          inbound_orders_status["pickup_done"] +
                                          inbound_orders_status["created"])

    # ── 7. Validate & Write dispatch JSONs ────────────────────────
    print(f"\n📤 Validating Data Contract & Writing JSON files → {DATA_DIR}")
    validate_payload_contract(inbound_json, "inbound.json / latest.json.gz")
    validate_payload_contract(inventory_json, "inventory.json")

    micro_payloads = {
        "inbound_kpi_summary.json": inbound_kpi_summary,
        "inbound_hourly_trend.json": inbound_hourly_trend,
        "inbound_orders_status.json": inbound_orders_status,
        "inbound_truck_eta.json": inbound_truck_eta,
        "inbound_origin_station.json": inbound_origin_station,
    }

    # Write root data/ files
    write_json("inventory.json",          inventory_json)
    write_json("outbound.json",           outbound_json)
    write_json("backlog.json",            backlog_json)
    write_json("inbound.json",            inbound_json)
    write_json("arrival.json",            arrival_json)
    write_json("heatmap.json",            hourly)
    write_json("hub_inventory_pivot.json",hub_pivot_json)
    write_json("last_update.json",        last_update_obj)
    write_json("linehaul.json",           linehaul_obj)
    write_json("truck_eta.json",          truck_eta_obj)

    for fn, pl in micro_payloads.items():
        write_json(fn, pl)

    # Write live/ and history/{today}/ files
    live_rel = os.path.join(DATA_DIR, "live")
    hist_rel = os.path.join(DATA_DIR, "history", today)
    os.makedirs(live_rel, exist_ok=True)
    os.makedirs(hist_rel, exist_ok=True)

    for fn, pl in micro_payloads.items():
        write_json(os.path.join("live", fn), pl)
        write_json(os.path.join("history", today, fn), pl)

    # 🛑 BẢO VỆ NGÀY LỊCH SỬ: Tạo & Chốt khoá cứng 100% file snapshot lịch sử cho các ngày quá khứ (< today)
    try:
        conn_hist = get_pg_conn()
        cur_h = conn_hist.cursor()
        cur_h.execute("""
            SELECT DISTINCT COALESCE(op_date_pickup::date, operation_date_created::date)::text
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) IS NOT NULL
              AND COALESCE(op_date_pickup::date, operation_date_created::date)::text < %s
            ORDER BY 1 DESC;
        """, (today,))
        past_dates = [r[0] for r in cur_h.fetchall()]
        for h_d in past_dates:
            cur_h.execute("""
                SELECT 
                    (SELECT COUNT(DISTINCT tracking) FROM raw.scan_logs WHERE scan_time >= (%s::date + INTERVAL '6 hours') AND scan_time < (%s::date + INTERVAL '30 hours') AND scan_type = 'INBOUND') as inbound_cnt,
                    (SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created::date = %s::date AND status_sys = 'Transporting') as transp_cnt,
                    (SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE op_date_pickup::date = %s::date AND status_sys = 'Pickup Done') as pickup_cnt,
                    (SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created::date = %s::date AND status_sys = 'Created') as created_cnt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE (operation_date_inbound::date = %s::date OR (is_rebound = 1 AND operation_date_inbound_2::date = %s::date))) as inb_wt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE operation_date_created::date = %s::date AND status_sys = 'Transporting') as transp_wt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE op_date_pickup::date = %s::date AND status_sys = 'Pickup Done') as pickup_wt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE operation_date_created::date = %s::date AND status_sys = 'Created') as created_wt,
                    (SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date AND NOT (next_station LIKE 'BN HUB%%' OR next_station LIKE 'HN %%' OR next_station LIKE 'HD %%' OR next_station LIKE 'HY %%')) as shuttle_cnt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date AND NOT (next_station LIKE 'BN HUB%%' OR next_station LIKE 'HN %%' OR next_station LIKE 'HD %%' OR next_station LIKE 'HY %%')) as shuttle_wt,
                    (SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date AND (next_station LIKE 'BN HUB%%' OR next_station LIKE 'HN %%' OR next_station LIKE 'HD %%' OR next_station LIKE 'HY %%')) as linehaul_cnt,
                    (SELECT COALESCE(SUM(orders_weight), 0) / 1000.0 FROM enriched.dispatch_enriched WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date AND (next_station LIKE 'BN HUB%%' OR next_station LIKE 'HN %%' OR next_station LIKE 'HD %%' OR next_station LIKE 'HY %%')) as linehaul_wt;
            """, (h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d, h_d))
            h_row = cur_h.fetchone()
            if h_row:
                inb_c, tr_c, pk_c, cr_c, inb_w, tr_w, pk_w, cr_w, shut_c, shut_w, lh_c, lh_w = h_row
                inb_c, tr_c, pk_c, cr_c = int(inb_c or 0), int(tr_c or 0), int(pk_c or 0), int(cr_c or 0)
                inb_w, tr_w, pk_w, cr_w = round(float(inb_w or 0), 3), round(float(tr_w or 0), 3), round(float(pk_w or 0), 3), round(float(cr_w or 0), 3)
                shut_c, lh_c = int(shut_c or 0), int(lh_c or 0)
                shut_w, lh_w = round(float(shut_w or 0), 3), round(float(lh_w or 0), 3)
                
                h_kpi = {
                    "op_date": h_d,
                    "contract_version": "2.0.0",
                    "inbound_orders": inb_c,
                    "inbound_weight_ton": inb_w,
                    "forecast_total": shut_c + lh_c,
                    "forecast_weight_ton": round(shut_w + lh_w, 3),
                    "shuttle": shut_c,
                    "shuttle_weight": shut_w,
                    "linehaul": lh_c,
                    "linehaul_weight": lh_w,
                    "orders_now": cr_c,
                    "orders_live": tr_c + pk_c
                }
                h_status = {
                    "op_date": h_d,
                    "contract_version": "2.0.0",
                    "inbound": inb_c,
                    "transporting": tr_c,
                    "pickup_done": pk_c,
                    "created": cr_c,
                    "total": inb_c + tr_c + pk_c + cr_c,
                    "inbound_weight": inb_w,
                    "transporting_weight": tr_w,
                    "pickup_done_weight": pk_w,
                    "created_weight": cr_w
                }
                for h_root in [DATA_DIR, os.path.normpath(os.path.join(DATA_DIR, '..', 'public', 'data')), os.path.normpath(os.path.join(DATA_DIR, '..', 'src', 'data'))]:
                    h_path = os.path.join(h_root, "history", h_d)
                    os.makedirs(h_path, exist_ok=True)
                    target_status_file = os.path.join(h_path, "inbound_orders_status.json")
                    
                    # BẢO VỆ TUYỆT ĐỐI NGÀY LỊCH SỬ: Nếu file đã có dữ liệu hợp lệ, KHÔNG GHI ĐÈ bằng 0!
                    if os.path.exists(target_status_file):
                        try:
                            with open(target_status_file, 'r', encoding='utf-8') as f_exist:
                                existing_data = json.load(f_exist)
                            existing_tot = int(existing_data.get('total', 0) or 0)
                            existing_inb = int(existing_data.get('inbound', 0) or 0)
                            new_tot = int(h_status.get('total', 0) or 0)
                            new_inb = int(h_status.get('inbound', 0) or 0)
                            if (new_tot == 0 and existing_tot > 0) or (new_inb == 0 and existing_inb > 0):
                                continue  # BẢO VỆ SNAPSHOT LỊCH SỬ! BỎ QUA GHI ĐÈ.
                        except Exception:
                            pass

                    write_json(os.path.join(h_path, "inbound_kpi_summary.json"), h_kpi)
                    write_json(target_status_file, h_status)
        conn_hist.close()
    except Exception as _e_h:
        print(f"   ⚠️ Historical snapshot generation error: {_e_h}")

    # Sync to public/data & src/data
    json_files_to_sync = ["inventory.json", "outbound.json", "backlog.json", "inbound.json", "arrival.json", "heatmap.json", "hub_inventory_pivot.json", "last_update.json", "linehaul.json", "truck_eta.json"] + list(micro_payloads.keys())
    
    for sub in ['public/data', 'src/data']:
        sub_dir = os.path.normpath(os.path.join(DATA_DIR, '..', sub))
        sub_live = os.path.join(sub_dir, 'live')
        sub_hist = os.path.join(sub_dir, 'history', today)
        os.makedirs(sub_live, exist_ok=True)
        os.makedirs(sub_hist, exist_ok=True)
        
        if os.path.exists(sub_dir):
            import shutil
            for jf in json_files_to_sync:
                src_p = os.path.join(DATA_DIR, jf)
                dst_p = os.path.join(sub_dir, jf)
                if os.path.exists(src_p):
                    shutil.copy2(src_p, dst_p)

            for m_fname in micro_payloads.keys():
                src_m = os.path.join(DATA_DIR, 'live', m_fname)
                if os.path.exists(src_m):
                    shutil.copy2(src_m, os.path.join(DATA_DIR, m_fname))
                    shutil.copy2(src_m, os.path.join(sub_dir, m_fname))
                    shutil.copy2(src_m, os.path.join(sub_live, m_fname))
                    shutil.copy2(src_m, os.path.join(sub_hist, m_fname))

    # Gzip inbound
    raw_bytes = json.dumps(inbound_json, ensure_ascii=False).encode('utf-8')
    gz_path   = os.path.join(DATA_DIR, "latest.json.gz")
    with gzip.open(gz_path, 'wb') as gz:
        gz.write(raw_bytes)
    print(f"   ✅ {'latest.json.gz':<42} {os.path.getsize(gz_path)//1024:>6} KB  |  {len(inbound_json):,} records")

    # ── 8. PostgreSQL 90-Day Retention Cleanup ────────────────────
    try:
        conn_clean = get_pg_conn()
        cur_clean  = conn_clean.cursor()
        cur_clean.execute("DELETE FROM raw.scan_logs WHERE scan_time < CURRENT_DATE - INTERVAL '90 days';")
        cur_clean.execute("DELETE FROM enriched.dispatch_enriched WHERE created_time < CURRENT_DATE - INTERVAL '90 days';")
        conn_clean.commit()
        cur_clean.close()
        conn_clean.close()
        print("   🧹 PostgreSQL 90-day retention cleanup completed successfully.")
    except Exception as _ec:
        print(f"   ⚠️ PostgreSQL 90-day cleanup error: {_ec}")

    # ── 9. Done ───────────────────────────────────────────────────
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
            "data/inventory.json", "data/outbound.json", "data/backlog.json",
            "data/inbound.json", "data/arrival.json", "data/heatmap.json",
            "data/linehaul.json", "data/truck_eta.json", "data/last_update.json",
            "data/hub_inventory_pivot.json", "data/latest.json.gz",
            "data/inbound_kpi_summary.json", "data/inbound_hourly_trend.json",
            "data/inbound_orders_status.json", "data/inbound_truck_eta.json",
            "data/inbound_origin_station.json", "data/live/", "data/history/",
            "public/data/", "src/data/live/", "src/data/history/",
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
