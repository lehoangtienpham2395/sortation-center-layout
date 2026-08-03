"""
BUILD MASTER PIPELINE v2.0 — Dual-Source Master Architecture (Live vs History)

1. Live Data (data/live/ & data/): Active daily operational data & ALL micro-JSONs.
2. Historical Snapshots (data/history/YYYY-MM-DD/): Frozen, immutable snapshots for completed shifts.
3. Volume (Backlog + Forecast): Live-only forecasting, strictly non-frozen.
4. Field Normalization: Both `area_id` and `areaId` present for Layout Inventory rendering.
"""

import sys
import os
import time
import json
import datetime
import psycopg2

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

DATA_DIR = os.path.join(ROOT_DIR, "data")
PUBLIC_DATA_DIR = os.path.join(ROOT_DIR, "public", "data")
LIVE_DIR = os.path.join(DATA_DIR, "live")
PUBLIC_LIVE_DIR = os.path.join(PUBLIC_DATA_DIR, "live")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
PUBLIC_HISTORY_DIR = os.path.join(PUBLIC_DATA_DIR, "history")

for d in [DATA_DIR, PUBLIC_DATA_DIR, LIVE_DIR, PUBLIC_LIVE_DIR, HISTORY_DIR, PUBLIC_HISTORY_DIR]:
    os.makedirs(d, exist_ok=True)

def get_op_date_vn(dt=None):
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    today_str = dt.strftime("%Y-%m-%d")
    if dt.hour < 6:
        return (dt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return today_str

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_db_connection():
    passwords = ['Tien@giang0203', 'Tien@giang0203', 'postgres']
    for pwd in passwords:
        try:
            conn = psycopg2.connect(
                dbname='logistics_db',
                user='postgres',
                password=pwd,
                host='127.0.0.1',
                port=5433
            )
            return conn
        except Exception:
            continue
    raise Exception("Could not connect to PostgreSQL with any known password.")

def run_master_pipeline():
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    op_today = get_op_date_vn(now_vn)
    timestamp_str = now_vn.strftime("%H:%M:%S %d/%m/%Y")
    
    print(f"============================================================")
    print(f"🚀 [BUILD MASTER PIPELINE v2.0] Execution at {timestamp_str}")
    print(f"   Current Operating Date (op_today): {op_today}")
    print(f"============================================================")

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------------------
    # 1. Fetch Operating Dates in DB
    # -----------------------------------------------------------------
    cur.execute('''
        SELECT DISTINCT COALESCE(op_date_pickup::date, operation_date_created::date)::text
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) IS NOT NULL
        ORDER BY 1 DESC;
    ''')
    all_op_dates = [r[0] for r in cur.fetchall()]
    print(f"📊 Found {len(all_op_dates)} operating dates in database: {all_op_dates[:10]}...")

    # -----------------------------------------------------------------
    # 2. Build Inventory Data for Layout (Live)
    # -----------------------------------------------------------------
    cur.execute('''
        SELECT 
            COALESCE(round, '3') as zone,
            COALESCE(rank, 'A01') as area_id,
            COALESCE(next_station, pickup_station, 'KHO CHỜ') as station_name,
            COALESCE(status_sys, 'Created') as status,
            COUNT(*) as volume,
            ROUND((SUM(orders_weight) / 1000.0)::numeric, 5) as weight_ton,
            780 as capacity,
            %s as op_date
        FROM enriched.dispatch_enriched
        WHERE status_sys IN ('Inbound', 'Transporting', 'Created', 'Pickup Done')
          AND flag_outbound = 0
        GROUP BY 1, 2, 3, 4;
    ''', (op_today,))
    
    inv_rows = cur.fetchall()
    inventory_data = []
    for z, aid, st_name, st, vol, wt, cap, op_d in inv_rows:
        inventory_data.append({
            "zone": str(z),
            "area_id": str(aid),
            "areaId": str(aid),
            "station_name": str(st_name),
            "status": str(st),
            "volume": int(vol or 0),
            "weight_ton": float(wt or 0.0),
            "capacity": int(cap or 780),
            "op_date": str(op_d)
        })

    for path in [
        os.path.join(LIVE_DIR, "inventory.json"),
        os.path.join(DATA_DIR, "inventory.json"),
        os.path.join(PUBLIC_DATA_DIR, "inventory.json")
    ]:
        save_json(path, inventory_data)

    hours_list = [f"{h:02d}:00" for h in (list(range(6, 24)) + list(range(0, 6)))]
    daily_snapshots = {}

    # -----------------------------------------------------------------
    # 3. Generate ALL 5 Micro-JSONs for History vs Live
    # -----------------------------------------------------------------
    for d_str in all_op_dates:
        is_history = (d_str < op_today)
        is_frozen = is_history

        # A. 5 Milestone Progression Query
        # A. 5 Milestone Progression Query (Non-overlapping Waterfall Stages)
        cur.execute('''
            SELECT 
                SUM(CASE WHEN flag_inbound = 1 OR inbound_scandate IS NOT NULL THEN 1 ELSE 0 END) as inbound_cnt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 1 OR arrival_scandate IS NOT NULL) THEN 1 ELSE 0 END) as transp_cnt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 0 AND arrival_scandate IS NULL) AND (flag_pickup = 1 OR pickup_time IS NOT NULL) THEN 1 ELSE 0 END) as pickup_cnt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 0 AND arrival_scandate IS NULL) AND (flag_pickup = 0 AND pickup_time IS NULL) THEN 1 ELSE 0 END) as created_cnt,
                SUM(CASE WHEN flag_inbound = 1 OR inbound_scandate IS NOT NULL THEN orders_weight ELSE 0 END) / 1000.0 as inb_wt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 1 OR arrival_scandate IS NOT NULL) THEN orders_weight ELSE 0 END) / 1000.0 as transp_wt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 0 AND arrival_scandate IS NULL) AND (flag_pickup = 1 OR pickup_time IS NOT NULL) THEN orders_weight ELSE 0 END) / 1000.0 as pickup_wt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (flag_arrival = 0 AND arrival_scandate IS NULL) AND (flag_pickup = 0 AND pickup_time IS NULL) THEN orders_weight ELSE 0 END) / 1000.0 as created_wt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (UPPER(COALESCE(next_station, '')) = 'BN HUB' OR UPPER(COALESCE(rank, '')) = 'BN HUB' OR UPPER(COALESCE(round, '')) LIKE '%%LINEHAUL%%') THEN 1 ELSE 0 END) as linehaul_cnt,
                SUM(CASE WHEN (flag_inbound = 0 AND inbound_scandate IS NULL) AND (UPPER(COALESCE(next_station, '')) = 'BN HUB' OR UPPER(COALESCE(rank, '')) = 'BN HUB' OR UPPER(COALESCE(round, '')) LIKE '%%LINEHAUL%%') THEN orders_weight ELSE 0 END) / 1000.0 as linehaul_wt
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date;
        ''', (d_str,))

        def to_int(v):
            try: return int(v) if v is not None else 0
            except: return 0

        def to_float(v):
            try: return float(v) if v is not None else 0.0
            except: return 0.0

        row = cur.fetchone()
        inb_c = to_int(row[0]) if row else 0
        tr_c  = to_int(row[1]) if row else 0
        pk_c  = to_int(row[2]) if row else 0
        cr_c  = to_int(row[3]) if row else 0

        inb_w = round(to_float(row[4]), 3) if row else 0.0
        tr_w  = round(to_float(row[5]), 3) if row else 0.0
        pk_w  = round(to_float(row[6]), 3) if row else 0.0
        cr_w  = round(to_float(row[7]), 3) if row else 0.0

        lh_c  = to_int(row[8]) if row else 0
        lh_w  = round(to_float(row[9]), 3) if row else 0.0
        st_c  = max(0, (tr_c + pk_c + cr_c) - lh_c)
        st_w  = max(0.0, round((tr_w + pk_w + cr_w) - lh_w, 3))

        # B. Rot / Backlog breakdown
        prev_d_str = (datetime.datetime.strptime(d_str, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        cur.execute('''
            SELECT 
                flag_inbound, flag_outbound, status_sys, pickup_station, next_station, rank, round,
                COALESCE(op_date_pickup::text, operation_date_created::text) AS ref_date
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= %s::date;
        ''', (d_str,))
        
        rot_rows = cur.fetchall()
        rot_hom_truoc = 0
        rot_hom_nay = 0
        rot_ton_dong = 0

        for flag_in, flag_out, st_sys, pk_st, next_st, rk, rd, ref_d in rot_rows:
            stn = str(st_sys or '').strip()
            is_canceled = (stn == 'Đã hủy')
            pk_st_u = str(pk_st or '').upper()
            next_st_u = str(next_st or '').upper()
            rk_u = str(rk or '').upper()
            rd_u = str(rd or '').upper()

            is_north = ('BN HUB' in pk_st_u or 'BN HUB' in next_st_u or 'BN HUB' in rk_u or 'LINEHAUL' in rd_u or pk_st_u.startswith(('HN ', 'HD ', 'HY ')))
            is_rot = (not flag_in) and (not flag_out) and (not is_canceled) and (not is_north)

            if is_rot and ref_d:
                rf = str(ref_d)[:10]
                if rf == d_str:
                    rot_hom_nay += 1
                elif rf == prev_d_str:
                    rot_hom_truoc += 1
                elif rf < prev_d_str:
                    rot_ton_dong += 1

        daily_snapshots[d_str] = {
            "rot_hom_truoc": rot_hom_truoc,
            "rot_hom_nay": rot_hom_nay,
            "rot_ton_dong": rot_ton_dong,
            "is_frozen": is_frozen
        }

        # C. 1 - inbound_kpi_summary.json
        kpi_summary = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "inbound_orders": inb_c,
            "inbound_weight_ton": inb_w,
            "forecast_total": tr_c + pk_c + cr_c,
            "forecast_weight_ton": round(tr_w + pk_w + cr_w, 3),
            "shuttle_orders": st_c,
            "shuttle_weight": st_w,
            "linehaul_orders": lh_c,
            "linehaul_weight": lh_w,
            "rot_hom_truoc": rot_hom_truoc,
            "rot_hom_nay": rot_hom_nay,
            "linehaul_bn_hub": lh_c
        }

        # D. 2 - inbound_orders_status.json
        orders_status = {
            "op_date": d_str,
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

        # E. 3 - inbound_origin_station.json
        cur.execute('''
            SELECT 
                COALESCE(pickup_station, next_station, 'Bưu cục khác') as st_name,
                COUNT(*) as total_vol,
                SUM(CASE WHEN flag_inbound = 1 OR inbound_scandate IS NOT NULL THEN 1 ELSE 0 END) as inb_vol,
                SUM(CASE WHEN flag_arrival = 1 OR arrival_scandate IS NOT NULL THEN 1 ELSE 0 END) as tr_vol,
                SUM(CASE WHEN flag_pickup = 1 OR pickup_time IS NOT NULL THEN 1 ELSE 0 END) as pk_vol,
                COUNT(*) as cr_vol
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15;
        ''', (d_str,))
        st_rows = cur.fetchall()
        origin_stations = []
        for st_name, tot_v, inb_v, tr_v, pk_v, cr_v in st_rows:
            origin_stations.append({
                "station_name": str(st_name),
                "total_volume": int(tot_v or 0),
                "inbound_volume": int(inb_v or 0),
                "transporting_volume": int(tr_v or 0),
                "pickup_done_volume": int(pk_v or 0),
                "created_volume": int(cr_v or 0)
            })

        origin_station_payload = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "stations": origin_stations
        }

        # F. 4 - inbound_hourly_trend.json (Dynamic 24h Hourly Trend)
        cur.execute('''
            SELECT SUBSTRING(created_time::text FROM 12 FOR 2) || ':00' AS hr, COUNT(*)
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
              AND created_time IS NOT NULL
            GROUP BY 1;
        ''', (d_str,))
        cr_hr_map = dict(cur.fetchall())

        cur.execute('''
            SELECT SUBSTRING(pickup_time::text FROM 12 FOR 2) || ':00' AS hr, COUNT(*)
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
              AND pickup_time IS NOT NULL
            GROUP BY 1;
        ''', (d_str,))
        pk_hr_map = dict(cur.fetchall())

        cur.execute('''
            SELECT SUBSTRING(arrival_scandate::text FROM 12 FOR 2) || ':00' AS hr, COUNT(*)
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
              AND arrival_scandate IS NOT NULL
            GROUP BY 1;
        ''', (d_str,))
        arr_hr_map = dict(cur.fetchall())

        cur.execute('''
            SELECT SUBSTRING(inbound_scandate::text FROM 12 FOR 2) || ':00' AS hr, COUNT(*)
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
              AND inbound_scandate IS NOT NULL
            GROUP BY 1;
        ''', (d_str,))
        inb_hr_map = dict(cur.fetchall())

        hourly_trend_payload = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "hours": hours_list,
            "series": {
                "inbound": [inb_hr_map.get(h, 0) for h in hours_list],
                "transporting": [arr_hr_map.get(h, 0) for h in hours_list],
                "pickup_done": [pk_hr_map.get(h, 0) for h in hours_list],
                "created": [cr_hr_map.get(h, 0) for h in hours_list]
            }
        }

        # G. 5 - inbound_truck_eta.json
        cur.execute('''
            SELECT 
                COALESCE(pickup_station, 'BƯU CỤC NỘP') as send_net,
                'HCM004H' as arr_net,
                COALESCE(trip_code, 'TRIP_LIVE') as trip_c,
                COUNT(*) as ord_cnt,
                ROUND(SUM(orders_weight)::numeric, 2) as wt_kg,
                ROUND((SUM(orders_weight)/1000.0)::numeric, 4) as wt_ton
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date
            GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 20;
        ''', (d_str,))
        truck_rows = cur.fetchall()
        trucks_list = []
        for send_n, arr_n, tr_c, o_cnt, w_kg, w_ton in truck_rows:
            trucks_list.append({
                "send_network": str(send_n),
                "arrive_network": str(arr_n),
                "trip_code": str(tr_c),
                "orders_count": int(o_cnt or 0),
                "weight_kg": float(w_kg or 0.0),
                "weight_ton": float(w_ton or 0.0)
            })

        truck_eta_payload = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "trucks": trucks_list
        }

        # Save to target directories
        target_dirs = []
        if is_history:
            target_dirs.append(os.path.join(HISTORY_DIR, d_str))
            target_dirs.append(os.path.join(PUBLIC_HISTORY_DIR, d_str))
        else:
            target_dirs.append(LIVE_DIR)
            target_dirs.append(PUBLIC_LIVE_DIR)
            target_dirs.append(DATA_DIR)
            target_dirs.append(PUBLIC_DATA_DIR)

        for t_dir in target_dirs:
            save_json(os.path.join(t_dir, "inbound_kpi_summary.json"), kpi_summary)
            save_json(os.path.join(t_dir, "inbound_orders_status.json"), orders_status)
            save_json(os.path.join(t_dir, "inbound_origin_station.json"), origin_station_payload)
            save_json(os.path.join(t_dir, "inbound_hourly_trend.json"), hourly_trend_payload)
            save_json(os.path.join(t_dir, "inbound_truck_eta.json"), truck_eta_payload)

        fc_tot = to_int(tr_c) + to_int(pk_c) + to_int(cr_c)
        print(f"   [{'HIST' if is_history else 'LIVE'}] Date {d_str}: Inbound={inb_c:,}, Forecast={fc_tot:,}, Frozen={is_frozen}")

    # -----------------------------------------------------------------
    # 4. Save Master last_update.json
    # -----------------------------------------------------------------
    master_last_update = {
        "last_update": timestamp_str,
        "rot_hom_truoc": daily_snapshots.get(op_today, {}).get("rot_hom_truoc", 0),
        "rot_hom_nay": daily_snapshots.get(op_today, {}).get("rot_hom_nay", 0),
        "total_records": len(inventory_data),
        "daily_snapshots": daily_snapshots,
        "contract_version": "2.0.0"
    }

    for path in [
        os.path.join(LIVE_DIR, "last_update.json"),
        os.path.join(DATA_DIR, "last_update.json"),
        os.path.join(PUBLIC_DATA_DIR, "last_update.json")
    ]:
        save_json(path, master_last_update)

    conn.close()
    print("============================================================")
    print("✅ [BUILD MASTER PIPELINE v2.0] Success! All 5 Micro-JSONs written across Live & History.")
    print("============================================================")

if __name__ == '__main__':
    run_master_pipeline()
