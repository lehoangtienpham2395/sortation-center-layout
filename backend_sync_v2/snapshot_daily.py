"""
snapshot_daily.py — Daily 06:00 AM Historical Snapshot
=======================================================
Chot so ngay van hanh hom truoc, dong goi vao data/history/YYYY-MM-DD.json

Nguon du lieu: enriched.dispatch_enriched
Dieu kien: bat ky don nao co ref_date = yesterday (khong phan biet is_completed)
  - operation_date_inbound   = yesterday
  - op_date_pickup           = yesterday (tinh theo 06:00 boundary)
  - operation_date_created   = yesterday
  - DATE(outbound_scandate)  = yesterday (theo 06:00 boundary)
  - DATE(arrival_scandate)   = yesterday (theo 06:00 boundary)

Output: data/history/2026-07-27.json (write-once, khong bao gio ghi de)
        data/history_index.json      (cap nhat danh sach ngay)
Git push: chi 2 file moi, SKIP data/*.json rolling files
"""
import os, sys, io, json, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from sync_postgre import (
    get_pg_conn, get_sa_engine, get_op_date,
    clean_ts_str, is_valid_ts, write_json,
    PG_DBNAME, PG_HOST, PG_PORT,
    BASE_DIR, DATA_DIR, VALID_FILE
)
import pandas as pd

tz_vn     = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn    = datetime.datetime.now(tz_vn)
SNAP_DATE = (now_vn - datetime.timedelta(days=1)).strftime("%Y-%m-%d")  # ngay can chot
HIST_DIR  = os.path.join(DATA_DIR, "history")
HIST_FILE = os.path.join(HIST_DIR, f"{SNAP_DATE}.json")
IDX_FILE  = os.path.join(DATA_DIR, "history_index.json")

os.makedirs(HIST_DIR, exist_ok=True)


def should_skip() -> bool:
    """Khong chay neu file da ton tai (write-once protection)."""
    if os.path.exists(HIST_FILE):
        print(f"   SKIP — history/{SNAP_DATE}.json da ton tai (write-once)")
        return True
    return False


def load_valid_csv():
    dict_zone, dict_area, dict_station = {}, {}, {}
    if not os.path.exists(VALID_FILE):
        return dict_zone, dict_area, dict_station
    df_v = pd.read_csv(VALID_FILE, dtype=str)
    df_v.columns = df_v.columns.str.strip()
    sc_col   = next((c for c in ['sortcode','Ma tram','Dispatch_code'] if c in df_v.columns), None)
    area_col = next((c for c in ['area','AreaID'] if c in df_v.columns), None)
    st_col   = next((c for c in ['Buu cuc','Station_1','Station_2'] if c in df_v.columns), None)
    zone_col = next((c for c in ['Zone','Hubcode'] if c in df_v.columns), None)
    if sc_col and area_col:
        sc = df_v[sc_col].dropna().str.strip().str.upper()
        if zone_col: dict_zone    = dict(zip(sc, df_v[zone_col].fillna('3').str.strip()))
        dict_area    = dict(zip(sc, df_v[area_col].fillna('C01').str.strip()))
        if st_col:   dict_station = dict(zip(sc, df_v[st_col].fillna('').str.strip()))
    return dict_zone, dict_area, dict_station


def snapshot():
    print(f"\nSNAPSHOT {SNAP_DATE} — {now_vn.strftime('%H:%M:%S %d/%m/%Y')}")
    print("=" * 60)

    if should_skip():
        return

    # 1. Load valid.csv
    dict_zone, dict_area, dict_station = load_valid_csv()
    ZONE_MAP = {'SR0001':'1','BNI001':'1','1':'1','2':'2','3':'3'}

    # 2. Query PostgreSQL — moi don co ref_date = SNAP_DATE (khong loc is_completed)
    print(f"\nQuerying PostgreSQL for ngay van hanh {SNAP_DATE}...")
    query = f"""
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
            is_backlog, is_active, is_completed,
            cycle_no, is_rebound, return_count,
            inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
            last_updated
        FROM enriched.dispatch_enriched
        WHERE
            -- Moi don co hoat dong trong ngay van hanh hom qua
            operation_date_inbound   = '{SNAP_DATE}'
            OR operation_date_inbound_2 = '{SNAP_DATE}'
            OR operation_date_created   = '{SNAP_DATE}'
            OR (outbound_scandate IS NOT NULL AND
                CASE WHEN EXTRACT(HOUR FROM outbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                     THEN (outbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                     ELSE (outbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                END = '{SNAP_DATE}')
            OR (arrival_scandate IS NOT NULL AND
                CASE WHEN EXTRACT(HOUR FROM arrival_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                     THEN (arrival_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                     ELSE (arrival_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                END = '{SNAP_DATE}')
            OR (pickup_time IS NOT NULL AND
                CASE WHEN EXTRACT(HOUR FROM pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6
                     THEN (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                     ELSE (pickup_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                END = '{SNAP_DATE}')
        ORDER BY created_time DESC
    """
    try:
        sa_engine = get_sa_engine()
        if sa_engine:
            df = pd.read_sql(query, sa_engine)
            sa_engine.dispose()
        else:
            import warnings
            conn = get_pg_conn()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                df = pd.read_sql(query, conn)
            conn.close()
    except Exception as e:
        print(f"   Query failed: {e}")
        return

    df = df.fillna('')
    print(f"   {len(df):,} don thuoc ngay van hanh {SNAP_DATE}")

    # 3. Aggregate: inbound, outbound, inventory, heatmap
    inbound_group  = {}
    outbound_group = {}
    inventory_snap = {}
    heatmap        = {f"{h:02d}:00": 0 for h in range(24)}
    summary = {
        "total_inbound": 0, "total_outbound": 0, "total_pickup": 0,
        "total_created": 0, "total_rebound": 0,
        "rot_hom_truoc": 0, "rot_hom_nay": 0
    }

    for _, r in df.iterrows():
        sc_raw   = str(r.get('dispatch_code', '')).strip().upper()
        next_st  = str(r.get('next_station', '')).strip()
        mapped   = dict_station.get(sc_raw, '')
        station  = mapped or (next_st if next_st and next_st != 'KHONG VUNG KHAC' else 'KHONG VUNG KHAC')
        zone     = ZONE_MAP.get(dict_zone.get(sc_raw, '3'), '3')
        area_id  = dict_area.get(sc_raw, 'C01')
        cap      = 1400 if area_id == 'A06' else 780

        wt_kg    = float(r.get('orders_weight') or 0)
        cr_t     = clean_ts_str(r.get('created_time'))
        pk_t     = clean_ts_str(r.get('pickup_time'))
        inb_t    = clean_ts_str(r.get('inbound_scandate'))
        outb_t   = clean_ts_str(r.get('outbound_scandate'))
        arr_t    = clean_ts_str(r.get('arrival_scandate'))
        transp_t = clean_ts_str(r.get('transporing_time'))
        trip     = str(r.get('trip_code', '')).strip()
        is_reb   = int(r.get('is_rebound') or 0)
        ret_cnt  = int(r.get('return_count') or 0)
        inb_t_2  = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t_2 = clean_ts_str(r.get('outbound_scandate_2'))
        op_inb_2 = str(r.get('operation_date_inbound_2') or '')[:10]

        has_in  = bool(inb_t)
        has_out = bool(outb_t)
        has_pick = bool(pk_t)
        has_arr = bool(arr_t)

        op_inb  = str(r.get('operation_date_inbound') or '')[:10]
        op_fc   = get_op_date(cr_t)
        op_pick = get_op_date(pk_t)
        op_arr  = get_op_date(arr_t)
        op_outb = get_op_date(outb_t)

        final_op_inb = op_inb_2 if (is_reb and op_inb_2) else (op_inb if inb_t else '')
        final_inb_hour = inb_t_2[11:16] if (is_reb and len(inb_t_2) >= 16) else (inb_t[11:16] if len(inb_t) >= 16 else '')

        # Summary counters
        if has_in or (is_reb and inb_t_2): summary["total_inbound"] += 1
        if has_out or outb_t_2:            summary["total_outbound"] += 1
        if has_pick:                       summary["total_pickup"] += 1
        if not has_pick:                   summary["total_created"] += 1
        if is_reb:                         summary["total_rebound"] += 1

        # Rot flag (theo tiêu chí USER: tất cả đơn chưa về HUB, trừ Đã hủy)
        stn_raw = str(r.get('status_sys', '')).strip()
        is_canceled = (stn_raw == 'Đã hủy')
        op_cr_date = str(r.get('operation_date_created') or '')[:10] or op_fc
        drop_type = ''
        if not has_in and not has_arr and not is_canceled:
            if op_cr_date == SNAP_DATE:
                summary["rot_hom_nay"] += 1
                drop_type = 'rot_today'
            elif op_cr_date and op_cr_date < SNAP_DATE:
                summary["rot_hom_truoc"] += 1
                drop_type = 'rot_yesterday'

        # Inbound records
        in_status = ('Inbound' if (has_in or is_reb) else
                     'Transporting' if has_arr else
                     'Pickup Done' if has_pick else 'Created')
        drop_type = ''
        if has_pick and not has_in and not has_arr and not is_reb:
            drop_type = 'rot_today' if op_pick == SNAP_DATE else 'rot_yesterday'

        key_ib = (station, in_status, final_op_inb, op_fc, op_pick, op_arr,
                  final_inb_hour, cr_t[:16] if len(cr_t) >= 16 else '',
                  pk_t[:16] if len(pk_t) >= 16 else '',
                  arr_t[:16] if len(arr_t) >= 16 else '',
                  drop_type, trip, transp_t, is_reb)
        if key_ib not in inbound_group:
            inbound_group[key_ib] = {'volume': 0, 'weight_ton': 0.0, 'return_count': ret_cnt}
        inbound_group[key_ib]['volume']    += 1
        inbound_group[key_ib]['weight_ton'] += round(wt_kg / 1000, 4)

        # Outbound records
        if has_out and op_outb == SNAP_DATE:
            ko = (zone, area_id, station)
            if ko not in outbound_group:
                outbound_group[ko] = {'volume': 0, 'weight_ton': 0.0, 'capacity': cap}
            outbound_group[ko]['volume']    += 1
            outbound_group[ko]['weight_ton'] += round(wt_kg / 1000, 4)

        # Inventory snapshot (ton kho tai 05:59 truoc khi mo ca moi)
        if has_in and not has_out and not is_reb:
            ki = (zone, area_id, station)
            if ki not in inventory_snap:
                inventory_snap[ki] = {'volume': 0, 'weight_ton': 0.0, 'capacity': cap}
            inventory_snap[ki]['volume']    += 1
            inventory_snap[ki]['weight_ton'] += round(wt_kg / 1000, 4)

        # Heatmap
        if inb_t and final_op_inb == SNAP_DATE:
            hr = inb_t[11:13]
            key_h = f"{hr}:00" if hr else ''
            if key_h in heatmap:
                heatmap[key_h] += 1

    # 4. Build JSON arrays
    inbound_json = [
        {
            "station_name": k[0], "status": k[1],
            "op_date_inbound": k[2], "op_date_forecast": k[3],
            "op_date_pickup": k[4], "op_date_arrival": k[5],
            "inbound_hour": k[6], "forecast_time": k[7],
            "pickup_time": k[8], "arrival_time": k[9],
            "drop_type": k[10], "trip_code": k[11],
            "transporing_time": k[12], "is_rebound": int(k[13]),
            "volume": v["volume"],
            "weight_ton": round(v["weight_ton"], 4),
            "return_count": v["return_count"]
        }
        for k, v in inbound_group.items()
    ]
    outbound_json = [
        {"zone": k[0], "area_id": k[1], "station_name": k[2],
         "op_date": SNAP_DATE, "volume": v["volume"],
         "weight_ton": round(v["weight_ton"], 4), "capacity": v["capacity"]}
        for k, v in outbound_group.items()
    ]
    inventory_json = [
        {"zone": k[0], "area_id": k[1], "station_name": k[2],
         "volume": v["volume"], "weight_ton": round(v["weight_ton"], 4),
         "capacity": v["capacity"]}
        for k, v in inventory_snap.items()
    ]

    # 5. Build snapshot object
    snapshot_obj = {
        "snapshot_date": SNAP_DATE,
        "snapped_at":    now_vn.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "summary":       summary,
        "heatmap":       heatmap,
        "inbound":       inbound_json,
        "outbound":      outbound_json,
        "inventory":     inventory_json,
    }

    # 6. Write file (write-once)
    os.makedirs(HIST_DIR, exist_ok=True)
    with open(HIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(snapshot_obj, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(HIST_FILE) / 1024
    print(f"   Written: history/{SNAP_DATE}.json  ({size_kb:.1f} KB)")
    print(f"   Summary: Inbound={summary['total_inbound']:,}  Outbound={summary['total_outbound']:,}  Rebound={summary['total_rebound']:,}")
    print(f"   Rot: hom_truoc={summary['rot_hom_truoc']:,}  hom_nay={summary['rot_hom_nay']:,}")

    # 7. Update history_index.json
    idx = {"available_dates": []}
    if os.path.exists(IDX_FILE):
        try:
            with open(IDX_FILE, encoding='utf-8') as f:
                idx = json.load(f)
        except Exception:
            pass
    if SNAP_DATE not in idx.get("available_dates", []):
        idx["available_dates"].insert(0, SNAP_DATE)
        idx["available_dates"].sort(reverse=True)
    with open(IDX_FILE, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    print(f"   Updated: history_index.json ({len(idx['available_dates'])} dates)")

    # 8. Git push chi 2 file moi (KHONG push rolling data/*.json)
    print("\nGit push history files...")
    try:
        subprocess.run(["git", "add",
                        f"data/history/{SNAP_DATE}.json",
                        "data/history_index.json"],
                       cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
        status = subprocess.run(["git", "status", "--porcelain"],
                                cwd=BASE_DIR, capture_output=True, text=True)
        if not status.stdout.strip():
            print("   No changes to commit")
            return
        msg = f"chore(history): snapshot {SNAP_DATE} — {summary['total_inbound']:,} inbound, {summary['total_outbound']:,} outbound"
        subprocess.run(["git", "commit", "-m", msg],
                       cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
        push = subprocess.run(["git", "push", "origin", "main"],
                              cwd=BASE_DIR, capture_output=True, text=True, timeout=60)
        if push.returncode == 0:
            print(f"   Git push OK — history/{SNAP_DATE}.json live!")
        else:
            print(f"   Git push failed: {push.stderr.strip()[:200]}")
    except Exception as e:
        print(f"   Git error: {e}")

    print(f"\nSNAPSHOT {SNAP_DATE} DONE!")


if __name__ == '__main__':
    snapshot()
