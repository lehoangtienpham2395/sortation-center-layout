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
    return str(val).strip() if is_valid_ts(val) else ""

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
            "op_date":          get_op_date(actual_arr or actual_dep or now_sys),
        }
        # Dedup: ưu tiên record đã arrived
        if tc not in seen or (actual_arr and not seen[tc].get('actual_arrival')):
            seen[tc] = entry

    trucks = sorted(seen.values(), key=lambda x: x.get('actual_arrival') or x.get('planned_arrival') or '', reverse=True)
    print(f"   ✅ Linehaul: {len(trucks)} trips")
    return {"generated_at": now_sys, "total_trucks": len(trucks), "trucks": trucks}


def fetch_truck_eta_json(session, token_mgr) -> dict:
    """
    Gọi pull_shuttle từ hôm nay -> ngày mai → lọc xe CHƯA arrived & chỉ lấy chuyến từ hôm nay.
    """
    try:
        today_start = today + ' 00:00:00'
        recs = pull_shuttle(session, token_mgr, today_start, end_plus1)
    except Exception as e:
        print(f"   ⚠️  pull_shuttle failed: {e}")
        recs = []

    trucks = []
    for row in recs:
        actual_arr = str(row.get('actualArrivalTime') or '').strip()
        if actual_arr:          # bỏ xe đã đến
            continue

        p_dep = str(row.get('plannedDepartureTime') or row.get('createTime') or '').strip()
        # Bỏ qua các chuyến lên lịch trước ngày hôm nay
        if p_dep and p_dep[:10] < today:
            continue

        actual_dep = str(row.get('actualDepartureTime') or row.get('appDepartureTime') or '').strip()
        status     = 'in_transit' if actual_dep else 'loading'
        trip       = str(row.get('shipmentNo') or row.get('taskNo') or '').strip().upper()
        src        = str(row.get('ngon_anh_xa') or '').lower()
        rank       = 'Linehaul' if 'linehaul' in src else 'Shuttle'

        send_net = str(row.get('sendNetworkName') or row.get('startName') or '').strip()
        arr_net  = str(row.get('arriveNetworkName') or row.get('endName') or '').strip()

        trucks.append({
            "send_network":     send_net,
            "arrive_network":   arr_net,
            "trip_code":        trip,
            "orders_count":     int(row.get('loadscanwaybillnum')   or 0),
            "weight_kg":        float(row.get('loadpackageweight')  or 0),
            "planned_departure":p_dep,
            "planned_arrival":  str(row.get('plannedArrivalTime')   or '').strip(),
            "actual_departure": actual_dep,
            "eta":              str(row.get('estimateArrivalTime')  or '').strip(),
            "rank":             rank,
            "status":           status,
            "op_date":          today,
        })

    trucks.sort(key=lambda x: x.get('eta') or x.get('planned_departure') or '9999')
    print(f"   ✅ Truck ETA (en route today/tomorrow): {len(trucks)} trucks")
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

    # ── 2. PostgreSQL fetch & export ──────────────────────────────────────────
    print("\n📦 Phase 2: Reading from PostgreSQL logistics_db & generating JSONs...")
    try:
        conn = get_pg_conn()
        print("   🟢 Connected to PostgreSQL")
    except Exception as e:
        print(f"   ❌ Cannot connect: {e}")
        return

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
            is_backlog, is_active
        FROM enriched.dispatch_enriched
        WHERE operation_date_created >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY operation_date_created DESC, created_time DESC
    """
    try:
        df = pd.read_sql(query, conn)
        conn.close()
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        conn.close()
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

    # Normalize Hubcode → numeric zone for frontend ZONE_LIST
    ZONE_MAP = {'SR0001': '1', 'BNI001': '1', '1': '1', '2': '2', '3': '3'}

    for _, r in df.iterrows():
        sc_raw    = str(r.get('dispatch_code', '')).strip().upper()
        sc        = sc_raw
        next_st   = str(r.get('next_station',  '')).strip()
        mapped_st = dict_station.get(sc, '')
        station   = mapped_st or (next_st if next_st and next_st != 'KHÔ VÙNG KHÁC' else 'KHÔ VÙNG KHÁC')
        zone      = ZONE_MAP.get(dict_zone.get(sc, '3'), '3')
        area_id   = dict_area.get(sc)
        valid_area = area_id is not None
        area_id   = area_id or 'C01'
        cap       = 780

        if area_id == 'A06':
            station, zone, cap = 'BN HUB', '1', 1400

        wt_kg    = float(r.get('orders_weight') or 0)
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

        # Inventory status (trùng khớp 100% với bộ lọc Control Center trong React UI)
        inv_status = ('Outbound'      if has_out else
                      'Inbound'       if has_in  else
                      'Transporting'  if has_arr else 'Created')

        # inventory group — CHỈ đơn CHƯA RỜI HUB và có area_id hợp lệ
        if not has_out and valid_area:
            ki = (zone, area_id, station, inv_status)
            if ki not in inv_group:
                inv_group[ki] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            inv_group[ki]['volume']    += 1
            inv_group[ki]['weight_kg'] += wt_kg

        # outbound group — chỉ record có area_id hợp lệ và tính chuẩn ngày vận hành xuất kho (op_date_outb)
        if has_out and valid_area:
            op_date_outb = get_op_date(outb_t)
            if op_date_outb in (today, yesterday):
                ko = (zone, area_id, station, op_date_outb)
                if ko not in out_group:
                    out_group[ko] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
                out_group[ko]['volume']    += 1
                out_group[ko]['weight_kg'] += wt_kg

        # backlog group — chỉ record có area_id hợp lệ
        if has_in and not has_out and valid_area:
            kb = (zone, area_id, station)
            if kb not in backlog_group:
                backlog_group[kb] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            backlog_group[kb]['volume']    += 1
            backlog_group[kb]['weight_kg'] += wt_kg

        # inbound (2 ngày gần nhất để giữ file nhỏ)
        op_date_inb  = get_op_date(inb_t)  if inb_t  else ''
        op_date_fc   = get_op_date(cr_t)   if cr_t   else ''
        op_date_pick = get_op_date(pk_t)   if pk_t   else ''
        op_date_arr  = get_op_date(arr_t)  if arr_t  else ''

        if op_date_inb in (today, yesterday) or op_date_fc in (today, yesterday):
            in_status  = ('Inbound'      if has_in   else
                          'Transporting' if has_arr  else
                          'Created'      if has_pick else 'Created')
            drop_type  = 'rot_today' if op_date_fc == today else 'rot_yesterday'
            key_ib = (
                station, in_status,
                op_date_inb, op_date_fc, op_date_pick, op_date_arr,
                inb_t[11:16]  if len(inb_t)  >= 16 else '',
                cr_t[:16]     if len(cr_t)   >= 16 else '',
                pk_t[:16]     if len(pk_t)   >= 16 else '',
                arr_t[:16]    if len(arr_t)  >= 16 else '',
                drop_type, trip, transp_t, transpd_t,
            )
            if key_ib not in inbound_group:
                inbound_group[key_ib] = {'volume': 0, 'weight_kg': 0.0}
            inbound_group[key_ib]['volume']    += 1
            inbound_group[key_ib]['weight_kg'] += wt_kg

        # arrival
        if arr_t:
            op_d   = get_op_date(arr_t)
            scan_h = arr_t[:13] + ":00" if len(arr_t) >= 13 else arr_t
            ka     = (op_d, station, scan_h)
            if ka not in arr_group:
                arr_group[ka] = {'total': 0, 'at_hub': 0, 'not_hub': 0, 'last_scan_time': arr_t}
            arr_group[ka]['total'] += 1
            arr_group[ka]['at_hub' if has_in else 'not_hub'] += 1
            if arr_t > arr_group[ka]['last_scan_time']:
                arr_group[ka]['last_scan_time'] = arr_t

        # heatmap — inbound hôm nay
        if inb_t and op_date_inb == today and len(inb_t) >= 13:
            hk = inb_t[11:13] + ":00"
            if hk in hourly:
                hourly[hk] += 1

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
        {"station_name": st, "status": status,
         "volume": stats['volume'], "weight_ton": round(stats['weight_kg'] / 1000, 3),
         "op_date_inbound": in_op, "op_date_forecast": fc_op,
         "op_date_pickup": pk_op, "op_date_arrival": ar_op,
         "inbound_hour": in_hr, "forecast_time": fc_hr,
         "pickup_time": pk_hr, "arrival_time": ar_hr,
         "drop_type": drop_t, "trip_code": tc,
         "transporing_time": tr_t, "transported_time": trd_t}
        for (st, status, in_op, fc_op, pk_op, ar_op,
             in_hr, fc_hr, pk_hr, ar_hr,
             drop_t, tc, tr_t, trd_t), stats in inbound_group.items()
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
    last_update_obj = {
        "last_update":           now_display,
        "active_date":           today,
        "yesterday":             yesterday,
        "total_records":         len(df),
        "total_inbound_today":   int(hourly.get('06:00', 0) + sum(hourly.values())),
        "total_backlog":         len(backlog_json),
        "total_inventory":       len(inventory_json),
        "rot_hom_truoc":         0,
        "rot_hom_nay":           0,
        "sync_success":          True,
    }

    # ── 5. Write dispatch JSONs ───────────────────────────────────
    print(f"\n📤 Writing JSON files → {DATA_DIR}")
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
        # 1. git add data/ và src/ (chỉ JSON data + code thay đổi)
        add = subprocess.run(
            ["git", "add", "data/", "src/", "backend_sync/"],
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
