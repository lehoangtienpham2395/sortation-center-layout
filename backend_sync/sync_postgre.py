"""
sync_postgre.py — Engine xuất báo cáo dashboard từ PostgreSQL.

Luồng:
  Đọc enriched.dispatch_enriched (logistics_db) → tổng hợp → xuất 9 JSON vào data/:
    - inventory.json, outbound.json, backlog.json, inbound.json, arrival.json
    - last_update.json
    - heatmap.json        (mới)
    - linehaul.json       (giữ nguyên file cũ nếu có — cần JFS API, không có trong PG)
    - truck_eta.json      (mới, từ dữ liệu transporing/transported trong PG)

Dashboard (src/App.tsx) fetch các JSON này từ raw.githubusercontent.com/.../main/data/*.json
→ luồng 30 phút (auto_sync_schedule.py) gọi script này, sau đó git commit & push lên main.

Ghi chú: PG host=127.0.0.1, port=5433, db=logistics_db, schema=enriched.dispatch_enriched
"""
import os, sys, io, json, datetime
from zoneinfo import ZoneInfo

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# PostgreSQL connection (logistics_db)
PG_DBNAME = os.environ.get("PGDATABASE", "logistics_db")
PG_USER   = os.environ.get("PGUSER", "postgres")
PG_PASS   = os.environ.get("PGPASSWORD", "Tien@giang0203")
PG_HOST   = os.environ.get("PGHOST", "127.0.0.1")
PG_PORT   = int(os.environ.get("PGPORT", 5433))

VALID_FILE = os.path.join(BASE_DIR, "backend_sync", "config", "valid.csv")

tz_vn  = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn = datetime.datetime.now(tz_vn)
today_str = now_vn.strftime("%Y-%m-%d")
now_sys   = now_vn.strftime("%Y-%m-%d %H:%M:%S")

# Tên ngày tiếng Việt cho heatmap
DAYS_VN = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']


def get_op_date(dt_str):
    """Quy đổi sang operation_date: trước 06:00 thì thuộc ngày hôm trước."""
    if not dt_str or str(dt_str).lower() in ('nan', 'none', ''):
        return ""
    try:
        dt = datetime.datetime.strptime(str(dt_str)[:19], '%Y-%m-%d %H:%M:%S')
        if dt.hour < 6:
            return (dt.date() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return str(dt_str)[:10]


def load_pg():
    """Kết nối PostgreSQL. Raise nếu không được — không fallback SQLite nữa."""
    import psycopg2
    conn = psycopg2.connect(dbname=PG_DBNAME, user=PG_USER, password=PG_PASS,
                            host=PG_HOST, port=PG_PORT)
    print(f"🟢 Connected to PostgreSQL '{PG_DBNAME}' on port {PG_PORT}!")
    return conn


def load_valid_maps():
    """Đọc valid.csv → trả dict_zone / dict_area / dict_station / dict_rank."""
    dict_zone, dict_area, dict_station, dict_rank = {}, {}, {}, {}
    if os.path.exists(VALID_FILE):
        try:
            df_v = pd.read_csv(VALID_FILE, dtype=str)
            df_v.columns = df_v.columns.str.strip()
            sc = df_v['sortcode'].dropna().str.strip().str.upper()
            dict_zone    = dict(zip(sc, df_v['Hubcode'].fillna('3').str.strip()))
            dict_area    = dict(zip(sc, df_v['area'].fillna('C01').str.strip()))
            dict_station = dict(zip(sc, df_v['Station_2'].fillna('').str.strip()))
            dict_rank    = dict(zip(sc, df_v['Rank'].fillna('FC').str.strip()))
            print(f"   ✅ Nạp mapping sortcode từ valid.csv: {len(dict_zone)} bưu cục.")
        except Exception as e:
            print(f"   ⚠️ Lỗi nạp valid.csv: {e}")
    else:
        print(f"   ⚠️ Không tìm thấy valid.csv tại {VALID_FILE}")
    return dict_zone, dict_area, dict_station, dict_rank


def sync_postgre_to_dashboard():
    print(f"🚀 [{now_sys}] sync_postgre: đọc PG → xuất 9 JSON cho dashboard...")

    dict_zone, dict_area, dict_station, dict_rank = load_valid_maps()

    # === 1. ĐỌC POSTGRESQL ===
    conn = load_pg()
    df = pd.read_sql_query(
        "SELECT * FROM enriched.dispatch_enriched", conn
    )
    conn.close()
    if df.empty:
        print("   ⚠️ enriched.dispatch_enriched rỗng — không xuất JSON.")
        return False
    df = df.fillna('')
    # Ép toàn bộ cột về str an toàn (tránh NaT/None/float/datetime lẫn lộn)
    for c in df.columns:
        df[c] = df[c].map(lambda v: '' if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
        df[c] = df[c].replace({'NaT': '', 'nan': '', 'None': '', 'NaTT': ''})
    print(f"   Loaded {len(df):,} records từ enriched.dispatch_enriched.")

    # Ép kiểu số
    df['_orders_num'] = pd.to_numeric(df.get('orders_num', 1), errors='coerce').fillna(1).astype(int)
    df['_weight']     = pd.to_numeric(df.get('orders_weight', 0), errors='coerce').fillna(0.0).astype(float)

    # === 2. CHUẨN BỊ CỘT PHỤ ===
    # Gắn areacode / next_station đã được enrich trong PG sẵn; fallback từ dispatch_code
    df['_sc'] = df['dispatch_code'].astype(str).str.strip().str.upper()
    df['_station'] = df['next_station'].astype(str).str.strip()
    # Nếu next_station rỗng → tra từ valid
    mask_no_st = df['_station'] == ''
    df.loc[mask_no_st, '_station'] = df.loc[mask_no_st, '_sc'].map(dict_station).fillna('CHƯA PHÂN BƯU CỤC')
    df['_zone'] = df['_sc'].map(dict_zone).fillna('3')
    df['_area'] = df['_sc'].map(dict_area).fillna('C01')
    # Override BN HUB
    df.loc[df['_area'] == 'A06', '_station'] = 'BN HUB'
    df.loc[df['_area'] == 'A06', '_zone']    = 'BNI001'

    # Trạng thái / ngày vận hành
    df['_cr_t']  = df['created_time'].astype(str).str.strip()
    df['_pk_t']  = df['pickup_time'].astype(str).str.strip()
    df['_inb_t'] = df['inbound_scandate'].astype(str).str.strip()
    df['_out_t'] = df['outbound_scandate'].astype(str).str.strip()
    df['_arr_t'] = df['arrival_scandate'].astype(str).str.strip()
    df['_trp_t'] = df['transporing_time'].astype(str).str.strip()  # actualDepartureTime
    df['_tpd_t'] = df['transported_time'].astype(str).str.strip()  # actualArrivalTime
    df['_trip']  = df['trip_code'].astype(str).str.strip()

    df['_has_in']   = (df['_inb_t'] != '').astype(int)
    df['_has_out']  = (df['_out_t'] != '').astype(int)
    df['_has_arr']  = (df['_arr_t'] != '').astype(int)
    df['_has_pick'] = (df['_pk_t'] != '').astype(int)

    # === 3. INVENTORY (5 trạng thái) ===
    def inv_status(row):
        if row['_has_out']: return "Đã rời HUB"
        if row['_has_in']:  return "Đang trên bãi"
        if row['_has_arr']: return "Đang trên đường"
        if row['_has_pick']: return "Đã lấy hàng"
        return "Đã điều phối bưu cục"
    df['_inv_status'] = df.apply(inv_status, axis=1)

    g_inv = df.groupby(['_zone', '_area', '_station', '_inv_status']).agg(
        volume=('_orders_num', 'sum'), weight=('_weight', 'sum')
    ).reset_index()
    inventory_json = [{
        "Zone": r['_zone'], "AreaID": r['_area'], "Bu cc": r['_station'],
        "Trng thi": r['_inv_status'], "Volume": int(r['volume']),
        "Weight": round(float(r['weight']), 2), "Sc cha": 780, "Ngy": today_str
    } for r in g_inv.to_dict('records')]

    # === 4. OUTBOUND ===
    g_out = df[df['_has_out'] == 1].groupby(['_zone', '_area', '_station']).agg(
        volume=('_orders_num', 'sum'), weight=('_weight', 'sum')
    ).reset_index()
    outbound_json = [{
        "Zone": r['_zone'], "AreaID": r['_area'], "Bu cc": r['_station'],
        "Volume": int(r['volume']), "Weight": round(float(r['weight']), 2),
        "Sc cha": 780, "Ngy": today_str
    } for r in g_out.to_dict('records')]

    # === 5. BACKLOG (inbound + chưa outbound) ===
    g_bl = df[(df['_has_in'] == 1) & (df['_has_out'] == 0)].groupby(
        ['_zone', '_area', '_station']).agg(
        volume=('_orders_num', 'sum'), weight=('_weight', 'sum')
    ).reset_index()
    backlog_json = [{
        "Zone": r['_zone'], "AreaID": r['_area'], "Bu cc": r['_station'],
        "Volume": int(r['volume']), "Weight": round(float(r['weight']), 2),
        "Sc cha": 780, "Ngy": today_str
    } for r in g_bl.to_dict('records')]

    # === 6. INBOUND (gom nhóm theo trạng thái + khung giờ) ===
    def inb_status(row):
        if row['_has_in']:   return "Inbound"
        if row['_has_arr']:  return "Transporting"
        if row['_has_pick']: return "Pickup Done"
        return "Created"
    df['_inb_status'] = df.apply(inb_status, axis=1)
    df['_op_cr']  = df['_cr_t'].apply(get_op_date).replace('', today_str)
    df['_op_pk']  = df['_pk_t'].apply(lambda s: get_op_date(s) if s else "")
    df['_op_arr'] = df['_arr_t'].apply(lambda s: get_op_date(s) if s else "")
    df['_op_inb'] = df['_inb_t'].apply(lambda s: get_op_date(s) if s else "")
    df['_hr_in']  = df['_inb_t'].apply(lambda s: s[11:16] if len(s) >= 16 else "")
    df['_hr_cr']  = df['_cr_t'].apply(lambda s: s[:16] if len(s) >= 16 else "")
    df['_hr_pk']  = df['_pk_t'].apply(lambda s: s[:16] if len(s) >= 16 else "")
    df['_hr_arr'] = df['_arr_t'].apply(lambda s: s[:16] if len(s) >= 16 else "")
    df['_loi_rot'] = df['_op_cr'].apply(lambda d: "Rớt hôm nay" if d == today_str else "Rớt hôm trước")

    g_ib = df.groupby([
        '_station', '_inb_status', '_op_inb', '_op_cr', '_op_pk', '_op_arr',
        '_hr_in', '_hr_cr', '_hr_pk', '_hr_arr', '_loi_rot', '_trip', '_trp_t', '_tpd_t'
    ]).agg(volume=('_orders_num', 'sum'), weight=('_weight', 'sum')).reset_index()
    inbound_json = [{
        "Bu cc": r['_station'], "Trng thi": r['_inb_status'],
        "Volume": int(r['volume']), "Weight": round(float(r['weight']), 2),
        "Ngy vn hnh_Inbound": r['_op_inb'], "Ngy vn hnh_Forecast": r['_op_cr'],
        "Ngy vn hnh_Pickup": r['_op_pk'], "Ngy vn hnh_Arrival": r['_op_arr'],
        "Inbound Hour": r['_hr_in'], "Forecast Time": r['_hr_cr'],
        "Pickup Time": r['_hr_pk'], "Arrival Time": r['_hr_arr'],
        "Loi rt": r['_loi_rot'], "trip_code": r['_trip'],
        "transporing_time": r['_trp_t'], "transported_time": r['_tpd_t']
    } for r in g_ib.to_dict('records')]

    # === 7. ARRIVAL (gom theo op_date / station / scan_hour) ===
    df_arr = df[df['_arr_t'] != ''].copy()
    df_arr['_op_arr2'] = df_arr['_arr_t'].apply(get_op_date)
    df_arr['_scan_hr'] = df_arr['_arr_t'].apply(
        lambda s: s[:13] + ":00" if len(s) >= 13 else s)
    if not df_arr.empty:
        g_arr = df_arr.groupby(['_op_arr2', '_station', '_scan_hr']).agg(
            total=('_orders_num', 'sum'),
            at_hub=('_has_in', 'sum'),
            last_t=('_arr_t', 'max')
        ).reset_index()
        g_arr['_not_hub'] = g_arr['total'] - g_arr['at_hub']
        arrival_json = [{
            "Ngy vn hnh": r['_op_arr2'], "Ngày vận hành": r['_op_arr2'],
            "Pickup_station": r['_station'], "Station": r['_station'],
            "Scan Hour": r['_scan_hr'],
            "Tng s n": int(r['total']), "Tổng số đơn": int(r['total']),
            "Đã đến Hub": int(r['at_hub']), "Chưa đến Hub": int(r['_not_hub']),
            "Last time": r['last_t']
        } for r in g_arr.to_dict('records')]
    else:
        arrival_json = []

    # === 8. HEATMAP (grid op_date x 24h) ===
    heatmap_json = _build_heatmap(df)

    # === 9. TRUCK_ETA (xe đang vận chuyển: transporing có, transported chưa) ===
    truck_eta_json = _build_truck_eta(df)

    # === GHI 9 FILE JSON ===
    os.makedirs(DATA_DIR, exist_ok=True)
    _dump("inventory.json", inventory_json)
    _dump("outbound.json",  outbound_json)
    _dump("backlog.json",   backlog_json)
    _dump("inbound.json",   inbound_json)
    _dump("arrival.json",   arrival_json)
    _dump("heatmap.json",   heatmap_json)
    _dump("truck_eta.json", truck_eta_json)

    # linehaul.json: GIỮ NGUYÊN file cũ nếu có (cần JFS API, không có trong PG)
    lh_path = os.path.join(DATA_DIR, "linehaul.json")
    if os.path.exists(lh_path):
        print(f"   ♻️  Giữ nguyên linehaul.json hiện có ({os.path.getsize(lh_path)} bytes) — cần JFS API.")
    else:
        _dump("linehaul.json", {"total_trucks": 0, "trucks": []})
        print(f"   ⚠️ Tạo linehaul.json rỗng (chưa có dữ liệu JFS).")

    # last_update.json
    rot_hom_nay  = int(df[df['_op_cr'] == today_str]['_orders_num'].sum())
    rot_hom_trc  = int(df[df['_op_cr'] != today_str]['_orders_num'].sum())
    last_update_obj = {
        "last_update": now_vn.strftime('%H:%M:%S %d/%m/%Y'),
        "activeDate": today_str,
        "rot_hom_truoc": rot_hom_trc,
        "rot_hom_nay": rot_hom_nay,
        "source": "postgresql:enriched.dispatch_enriched",
        "rows": int(len(df))
    }
    with open(os.path.join(DATA_DIR, "last_update.json"), 'w', encoding='utf-8') as f:
        json.dump(last_update_obj, f, ensure_ascii=False, indent=2)
    print(f"   💾 Đã lưu last_update.json | rot_hom_nay={rot_hom_nay} rot_hom_truoc={rot_hom_trc}")

    print(f"🎉 sync_postgre hoàn tất! Đã xuất 9 JSON vào {DATA_DIR}")
    return True


def _build_heatmap(df):
    """Grid op_date (>= 2026-07-05) x 24h cho 5 event: created/pickup/transporting/inbound/outbound."""
    cols_map = [
        ('created',      '_cr_t'),
        ('pickup',       '_pk_t'),
        ('transporting', '_arr_t'),  # Arrival = transporting đến HUB
        ('inbound',      '_inb_t'),
        ('outbound',     '_out_t'),
    ]
    # Parse datetime
    parsed = {}
    for label, col in cols_map:
        parsed[label] = pd.to_datetime(df[col].replace('', pd.NA), errors='coerce')

    all_op_dates = set()
    for label, _ in cols_map:
        for dt in parsed[label].dropna():
            op = (dt - pd.Timedelta(days=1)) if dt.hour < 6 else dt
            op_str = op.strftime('%Y-%m-%d')
            if op_str >= '2026-07-05':
                all_op_dates.add(op_str)
    sorted_dates = sorted(all_op_dates, reverse=True)

    grid = {}
    for op_date in sorted_dates:
        dt_obj = pd.to_datetime(op_date)
        day_name = DAYS_VN[dt_obj.weekday()]
        for hr in range(24):
            grid[(op_date, hr)] = {
                'date': op_date, 'dayName': day_name, 'hour': f"{hr:02d}:00",
                'created': 0, 'pickup': 0, 'transporting': 0, 'inbound': 0, 'outbound': 0
            }

    def _op_hr(dt):
        op = (dt - pd.Timedelta(days=1)) if dt.hour < 6 else dt
        return op.strftime('%Y-%m-%d'), dt.hour

    for label, _ in cols_map:
        for dt in parsed[label].dropna():
            key = _op_hr(dt)
            if key in grid:
                grid[key][label] += 1
    return list(grid.values())


def _build_truck_eta(df):
    """Danh sách xe đang vận chuyển: có transporing_time nhưng chưa transported_time."""
    mask = (df['_trp_t'] != '') & (df['_tpd_t'] == '')
    df_tr = df[mask].copy()
    if df_tr.empty:
        return []
    g = df_tr.groupby(['_trip', '_station', '_trp_t']).agg(
        orders=('_orders_num', 'sum'),
        weight=('_weight', 'sum')
    ).reset_index()
    out = []
    for r in g.to_dict('records'):
        eta = ''
        op_dt = ''
        try:
            dt_send = pd.to_datetime(r['_trp_t'])
            dt_eta  = dt_send + pd.Timedelta(hours=36)
            eta    = dt_eta.strftime('%d/%m %H:%M')
            op_dt  = get_op_date(dt_eta.strftime('%Y-%m-%d %H:%M:%S'))
        except Exception:
            pass
        out.append({
            "Ngy vn hnh": op_dt, "Station": r['_station'], "Trucking": 1,
            "Orders": int(r['orders']), "weight": round(float(r['weight']), 2),
            "ETA": eta, "Rank": "Linehaul", "transfercode": r['_trip']
        })
    return out


def _dump(name, obj):
    path = os.path.join(DATA_DIR, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    n = len(obj) if isinstance(obj, list) else len(obj.get('trucks', []))
    print(f"   💾 Đã lưu {name} với {n} dòng.")


if __name__ == '__main__':
    ok = sync_postgre_to_dashboard()
    sys.exit(0 if ok else 1)
