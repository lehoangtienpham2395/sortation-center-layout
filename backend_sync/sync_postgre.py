import os, sys, io, json, datetime, sqlite3, pandas as pd
from zoneinfo import ZoneInfo

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dual Postgres/SQLite Connection
PG_URL = os.environ.get("POSTGRES_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip()
DB_FILE = os.path.join(BASE_DIR, "data", "dwh_v2.db")
DATA_DIR = os.path.join(BASE_DIR, "data")
VALID_FILE = r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv"
CSV_FILE = os.path.join(os.path.dirname(BASE_DIR), "full_multi_source_7days_v6.csv")

tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn = datetime.datetime.now(tz_vn)
today_str = now_vn.strftime("%Y-%m-%d")
now_sys = now_vn.strftime("%H:%M:%S %d/%m/%Y")

def get_op_date(dt_str):
    if not dt_str or str(dt_str).lower() in ('nan', 'none', ''): return ""
    try:
        dt = datetime.datetime.strptime(str(dt_str)[:19], '%Y-%m-%d %H:%M:%S')
        if dt.hour < 6:
            return (dt.date() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return str(dt_str)[:10]

def get_db_connection():
    if PG_URL:
        try:
            import psycopg2
            return psycopg2.connect(PG_URL)
        except Exception as e:
            print(f"⚠️ PostgreSQL Error ({e}), using local engine...")
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    return sqlite3.connect(DB_FILE)

def sync_postgre_to_dashboard():
    print(f"🚀 [{now_sys}] Running sync_postgre engine for Sortation Center Dashboard...")
    
    df_valid = pd.read_csv(VALID_FILE, dtype=str) if os.path.exists(VALID_FILE) else pd.DataFrame()
    dict_zone = {}
    dict_area = {}
    dict_station = {}
    if not df_valid.empty:
        df_valid.columns = df_valid.columns.str.strip()
        dict_zone = dict(zip(df_valid['sortcode'].dropna().str.strip().str.upper(), df_valid['Hubcode'].fillna('3').str.strip()))
        dict_area = dict(zip(df_valid['sortcode'].dropna().str.strip().str.upper(), df_valid['area'].fillna('C01').str.strip()))
        dict_station = dict(zip(df_valid['sortcode'].dropna().str.strip().str.upper(), df_valid['Station_2'].fillna('').str.strip()))

    if not os.path.exists(CSV_FILE):
        print(f"⚠️ Merged dataset {CSV_FILE} not found. Skipping export.")
        return

    df_v6 = pd.read_csv(CSV_FILE, dtype=str).fillna('')
    print(f"   Loaded {len(df_v6):,} records from v6 pipeline.")

    inv_group, out_group, backlog_group, inbound_group, arr_group = {}, {}, {}, {}, {}

    for r in df_v6.to_dict('records'):
        sc = r.get('Dispatch_code', '').strip().upper()
        next_st = r.get('Next_station', '').strip()
        st = next_st or dict_station.get(sc, 'CHƯA PHÂN BƯU CỤC')
        zn = dict_zone.get(sc, '3')
        area = dict_area.get(sc, 'C01')
        cap = '780'
        wt = float(r.get('Orders_weight') or 1.0)
        
        cr_t = r.get('Created_time', '').strip()
        pk_t = r.get('Pickup_time', '').strip()
        inb_t = r.get('inbound_scanDate', '').strip()
        outb_t = r.get('outbound_scanDate', '').strip()
        arr_t = r.get('arrival_scanDate', '').strip()
        trip = r.get('trip_code', '').strip()
        transp_t = r.get('transporing_time', '').strip()
        transpd_t = r.get('transported_time', '').strip()
        
        has_in = 1 if inb_t else 0
        has_out = 1 if outb_t else 0
        has_arr = 1 if arr_t else 0
        has_pick = 1 if pk_t else 0

        # Layout Inventory Statuses
        if has_out == 1: inv_status = "Đã rời HUB"
        elif has_in == 1: inv_status = "Đang trên bãi"
        elif has_arr == 1: inv_status = "Đang trên đường"
        elif has_pick == 1: inv_status = "Đã lấy hàng"
        else: inv_status = "Đã điều phối bưu cục"

        key_inv = (zn, area, st, inv_status)
        if key_inv not in inv_group: inv_group[key_inv] = {'volume': 0, 'weight': 0.0, 'capacity': cap}
        inv_group[key_inv]['volume'] += 1; inv_group[key_inv]['weight'] += wt

        if has_out == 1:
            key_out = (zn, area, st)
            if key_out not in out_group: out_group[key_out] = {'volume': 0, 'weight': 0.0, 'capacity': cap}
            out_group[key_out]['volume'] += 1; out_group[key_out]['weight'] += wt

        if has_in == 1 and has_out == 0:
            key_bl = (zn, area, st)
            if key_bl not in backlog_group: backlog_group[key_bl] = {'volume': 0, 'weight': 0.0, 'capacity': cap}
            backlog_group[key_bl]['volume'] += 1; backlog_group[key_bl]['weight'] += wt

        # Inbound Stage Statuses
        if has_in == 1: in_status = "Inbound"
        elif has_arr == 1: in_status = "Transporting"
        elif has_pick == 1: in_status = "Pickup Done"
        else: in_status = "Created"

        fc_op_date = get_op_date(cr_t) or today_str
        pk_op_date = get_op_date(pk_t) if pk_t else ""
        ar_op_date = get_op_date(arr_t) if arr_t else ""
        in_op_date = get_op_date(inb_t) if inb_t else ""

        fc_hr_str = cr_t[:16] if len(cr_t) >= 16 else ""
        pk_hr_str = pk_t[:16] if len(pk_t) >= 16 else ""
        ar_hr_str = arr_t[:16] if len(arr_t) >= 16 else ""
        in_hr_str = inb_t[11:16] if len(inb_t) >= 16 else ""
        loi_rot = "Rớt hôm nay" if fc_op_date == today_str else "Rớt hôm trước"

        key_ib = (st, in_status, in_op_date, fc_op_date, pk_op_date, ar_op_date, in_hr_str, fc_hr_str, pk_hr_str, ar_hr_str, loi_rot, trip, transp_t, transpd_t)
        if key_ib not in inbound_group: inbound_group[key_ib] = {'volume': 0, 'weight': 0.0}
        inbound_group[key_ib]['volume'] += 1; inbound_group[key_ib]['weight'] += wt

        # Arrival Aggregation
        if arr_t:
            op_d = get_op_date(arr_t)
            scan_hr = arr_t[:13] + ":00" if len(arr_t) >= 13 else arr_t
            key_ar = (op_d, st, scan_hr)
            if key_ar not in arr_group: arr_group[key_ar] = {'total': 0, 'at_hub': 0, 'not_hub': 0, 'last_t': arr_t}
            arr_group[key_ar]['total'] += 1
            if has_in == 1: arr_group[key_ar]['at_hub'] += 1
            else: arr_group[key_ar]['not_hub'] += 1
            if arr_t > arr_group[key_ar]['last_t']: arr_group[key_ar]['last_t'] = arr_t

    # Write Pivoted Layout JSONs
    inventory_json = [{"Zone": z, "AreaID": a, "Bu cc": s, "Trng thi": stt, "Volume": v['volume'], "Weight": round(v['weight'], 2), "Sc cha": v['capacity'], "Ngy": today_str} for (z, a, s, stt), v in inv_group.items()]
    outbound_json  = [{"Zone": z, "AreaID": a, "Bu cc": s, "Volume": v['volume'], "Weight": round(v['weight'], 2), "Sc cha": v['capacity'], "Ngy": today_str} for (z, a, s), v in out_group.items()]
    backlog_json   = [{"Zone": z, "AreaID": a, "Bu cc": s, "Volume": v['volume'], "Weight": round(v['weight'], 2), "Sc cha": v['capacity'], "Ngy": today_str} for (z, a, s), v in backlog_group.items()]

    inbound_json = [{
        "Bu cc": st, "Trng thi": status, "Volume": stats['volume'], "Weight": round(stats['weight'], 2),
        "Ngy vn hnh_Inbound": in_op, "Ngy vn hnh_Forecast": fc_op, "Ngy vn hnh_Pickup": pk_op, "Ngy vn hnh_Arrival": ar_op,
        "Inbound Hour": in_hr, "Forecast Time": fc_hr, "Pickup Time": pk_hr, "Arrival Time": ar_hr,
        "Loi rt": loi_rot, "trip_code": trip, "transporing_time": transp_t, "transported_time": transpd_t
    } for (st, status, in_op, fc_op, pk_op, ar_op, in_hr, fc_hr, pk_hr, ar_hr, loi_rot, trip, transp_t, transpd_t), stats in inbound_group.items()]

    arrival_json = [{
        "Ngy vn hnh": op_d, "Ngày vận hành": op_d, "Pickup_station": st, "Station": st, "Scan Hour": hr,
        "Tng s n": stats['total'], "Tổng số đơn": stats['total'], "Đã đến Hub": stats['at_hub'], "Chưa đến Hub": stats['not_hub'], "Last time": stats['last_t']
    } for (op_d, st, hr), stats in arr_group.items()]

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "inventory.json"), 'w', encoding='utf-8') as f: json.dump(inventory_json, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "outbound.json"), 'w', encoding='utf-8') as f: json.dump(outbound_json, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "backlog.json"), 'w', encoding='utf-8') as f: json.dump(backlog_json, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "inbound.json"), 'w', encoding='utf-8') as f: json.dump(inbound_json, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "arrival.json"), 'w', encoding='utf-8') as f: json.dump(arrival_json, f, ensure_ascii=False, indent=2)

    last_update_obj = {"last_update": now_sys, "activeDate": today_str}
    with open(os.path.join(DATA_DIR, "last_update.json"), 'w', encoding='utf-8') as f: json.dump(last_update_obj, f, ensure_ascii=False, indent=2)

    print("🎉 sync_postgre completed successfully!")

if __name__ == '__main__':
    sync_postgre_to_dashboard()
