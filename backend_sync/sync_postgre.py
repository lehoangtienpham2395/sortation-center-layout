"""
sync_postgre.py — Dashboard Data Pipeline
==========================================
Đọc từ PostgreSQL enriched.dispatch_enriched → xuất JSON files cho dashboard React.

Tích hợp JFS API từ pipeline_unified_v6.py (cùng thư mục scratch):
  - TokenManager, build_session, auth_post     → auth + retry
  - pull_linehaul_consol                        → linehaul.json
  - pull_shuttle                                → truck_eta.json (xe en-route)
  - pull_arrival                                → bổ sung arrival data từ API nếu cần

Field names: 100% English snake_case — không tiếng Việt có dấu hay bỏ dấu.

JSON outputs:
  data/inventory.json         — Tồn kho tổng hợp mọi trạng thái
  data/outbound.json          — Chỉ đơn has outbound_scandate
  data/backlog.json           — Đã inbound nhưng chưa outbound
  data/inbound.json           — Inbound tracking (2 ngày gần nhất, < 2MB)
  data/arrival.json           — Arrival scans group by op_date/station/hour
  data/heatmap.json           — {"HH:00": count} inbound by hour hôm nay
  data/linehaul.json          — Xe linehaul từ JFS API
  data/truck_eta.json         — Xe đang en-route (chưa đến)
  data/hub_inventory_pivot.json — Pivot tóm tắt cho layout map
  data/last_update.json       — Metadata + thống kê
  data/latest.json.gz         — inbound.json nén (lưu trữ)
"""

import os, sys, io, json, gzip, datetime, time as _time, threading, math
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

# ── Time ──────────────────────────────────────────────────────────────────────
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
    Gọi pull_shuttle → lọc xe CHƯA arrived → chuẩn hóa.
    {
      "generated_at": "...",
      "total_trucks_en_route": N,
      "trucks": [{
        "send_network", "arrive_network", "trip_code",
        "orders_count", "weight_kg",
        "planned_departure", "planned_arrival", "actual_departure",
        "eta", "rank", "status", "op_date"
      }]
    }
    """
    try:
        recs = pull_shuttle(session, token_mgr, start_str, end_plus1)
    except Exception as e:
        print(f"   ⚠️  pull_shuttle failed: {e}")
        recs = []

    trucks = []
    for row in recs:
        actual_arr = str(row.get('actualArrivalTime') or '').strip()
        if actual_arr:          # bỏ xe đã đến
            continue
        actual_dep = str(row.get('actualDepartureTime') or row.get('appDepartureTime') or '').strip()
        status     = 'in_transit' if actual_dep else 'loading'
        trip       = str(row.get('shipmentNo') or row.get('taskNo') or '').strip().upper()
        # Rank từ nguồn gốc: lh_ops có traceCode khác shuttle
        src  = str(row.get('ngon_anh_xa') or '').lower()
        rank = 'Linehaul' if 'linehaul' in src else 'Shuttle'
        trucks.append({
            "send_network":     str(row.get('sendNetworkName')      or '').strip(),
            "arrive_network":   str(row.get('arriveNetworkName')    or '').strip(),
            "trip_code":        trip,
            "orders_count":     int(row.get('loadscanwaybillnum')   or 0),
            "weight_kg":        float(row.get('loadpackageweight')  or 0),
            "planned_departure":str(row.get('plannedDepartureTime') or '').strip(),
            "planned_arrival":  str(row.get('plannedArrivalTime')   or '').strip(),
            "actual_departure": actual_dep,
            "eta":              str(row.get('estimateArrivalTime')  or '').strip(),
            "rank":             rank,
            "status":           status,
            "op_date":          today,
        })

    trucks.sort(key=lambda x: x.get('eta') or '9999')
    print(f"   ✅ Truck ETA (en route): {len(trucks)} trucks")
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

    # ── 1. Load valid.csv ─────────────────────────────────────────
    dict_zone, dict_area, dict_station = {}, {}, {}
    if os.path.exists(VALID_FILE):
        df_v = pd.read_csv(VALID_FILE, dtype=str)
        df_v.columns = df_v.columns.str.strip()
        sc = df_v['sortcode'].dropna().str.strip().str.upper()
        dict_zone    = dict(zip(sc, df_v['Hubcode'].fillna('3').str.strip()))
        dict_area    = dict(zip(sc, df_v['area'].fillna('C01').str.strip()))
        dict_station = dict(zip(sc, df_v['Station_2'].fillna('').str.strip()))
        print(f"   valid.csv : {len(dict_zone):,} sortcodes")
    else:
        print(f"   ⚠️  valid.csv not found — zone/area mapping empty")

    # ── 2. PostgreSQL fetch ───────────────────────────────────────
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
        WHERE is_active = 1
          AND operation_date_created >= CURRENT_DATE - INTERVAL '7 days'
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
    print(f"   📦 {len(df):,} records from PostgreSQL")

    # ── 3. Aggregate ──────────────────────────────────────────────
    inv_group     = {}   # (zone, area_id, station_name, status) → {volume, weight_kg, capacity}
    out_group     = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    backlog_group = {}   # (zone, area_id, station_name)         → {volume, weight_kg, capacity}
    inbound_group = {}   # 14-tuple key                          → {volume, weight_kg}
    arr_group     = {}   # (op_date, station_name, scan_hour)    → {total, at_hub, not_hub, last_scan_time}
    hourly        = {f"{h:02d}:00": 0 for h in range(24)}

    for _, r in df.iterrows():
        sc       = str(r.get('dispatch_code', '')).strip().upper()
        next_st  = str(r.get('next_station',  '')).strip()
        station  = next_st or dict_station.get(sc, 'UNKNOWN')
        zone     = dict_zone.get(sc, '3')
        area_id  = dict_area.get(sc, 'C01')
        cap      = 780

        if area_id == 'A06':
            station, zone, cap = 'BN HUB', 'BNI001', 1400

        wt_kg    = float(r.get('orders_weight') or 0)
        cr_t     = str(r.get('created_time',       '')).strip()
        pk_t     = str(r.get('pickup_time',         '')).strip()
        inb_t    = str(r.get('inbound_scandate',    '')).strip()
        outb_t   = str(r.get('outbound_scandate',   '')).strip()
        arr_t    = str(r.get('arrival_scandate',    '')).strip()
        trip     = str(r.get('trip_code',           '')).strip()
        transp_t = str(r.get('transporing_time',    '')).strip()
        transpd_t= str(r.get('transported_time',    '')).strip()
        op_date  = str(r.get('operation_date_created', today))[:10] or today

        has_in   = bool(inb_t)
        has_out  = bool(outb_t)
        has_arr  = bool(arr_t)
        has_pick = bool(pk_t)

        # Inventory status (trùng khớp 100% với bộ lọc Control Center trong React UI)
        inv_status = ('Đã xuất khỏi HUB'      if has_out else
                      'Đang trên bãi'         if has_in  else
                      'Đang trên đường'      if has_arr else
                      'Đã lấy hàng'           if has_pick else 'Đã điều phối bưu cục')

        # inventory group
        ki = (zone, area_id, station, inv_status)
        if ki not in inv_group:
            inv_group[ki] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
        inv_group[ki]['volume']    += 1
        inv_group[ki]['weight_kg'] += wt_kg

        # outbound group
        if has_out:
            ko = (zone, area_id, station)
            if ko not in out_group:
                out_group[ko] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            out_group[ko]['volume']    += 1
            out_group[ko]['weight_kg'] += wt_kg

        # backlog group
        if has_in and not has_out:
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
            in_status  = ('inbound'      if has_in   else
                          'transporting' if has_arr  else
                          'pickup_done'  if has_pick else 'created')
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
         "capacity": v['capacity'], "op_date": today}
        for (z, a, s), v in out_group.items()
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


if __name__ == '__main__':
    sync_postgre_to_dashboard()
