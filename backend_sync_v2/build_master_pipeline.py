"""
BUILD MASTER PIPELINE v2.0 — Dual-Source Master Architecture (Live vs History)

1. Live Data (data/live/ & data/): Active daily operational data & micro-JSONs.
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

DB_CONFIG = {
    'dbname': 'logistics_db',
    'user': 'postgres',
    'password': 'Tien@giang2299',
    'host': '127.0.0.1',
    'port': 5433
}

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
    passwords = ['Tien@giang0203', 'Tien@giang2299', 'postgres']
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
    print(f"📊 Found {len(all_op_dates)} operating dates in database: {all_op_dates}")

    # -----------------------------------------------------------------
    # 2. Build Inventory Data for Layout (Live)
    # -----------------------------------------------------------------
    # Query reporting.inventory_daily or active dispatch for inventory
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
            "areaId": str(aid), # Guaranteed camelCase mapping
            "station_name": str(st_name),
            "status": str(st),
            "volume": int(vol or 0),
            "weight_ton": float(wt or 0.0),
            "capacity": int(cap or 780),
            "op_date": str(op_d)
        })
    print(f"📦 Layout Inventory Live: {len(inventory_data)} mapped records ({sum(r['volume'] for r in inventory_data):,} total volume)")

    # Save live inventory.json
    for path in [
        os.path.join(LIVE_DIR, "inventory.json"),
        os.path.join(DATA_DIR, "inventory.json"),
        os.path.join(PUBLIC_DATA_DIR, "inventory.json")
    ]:
        save_json(path, inventory_data)

    # -----------------------------------------------------------------
    # 3. Generate Micro-JSONs & Full Data for History vs Live
    # -----------------------------------------------------------------
    daily_snapshots = {}

    for d_str in all_op_dates:
        is_history = (d_str < op_today)
        is_frozen = is_history

        # Inbound / Status Breakdown Query
        cur.execute('''
            SELECT 
                SUM(CASE WHEN status_sys = 'Inbound' THEN 1 ELSE 0 END) as inbound_cnt,
                SUM(CASE WHEN status_sys = 'Transporting' THEN 1 ELSE 0 END) as transp_cnt,
                SUM(CASE WHEN status_sys = 'Pickup Done' THEN 1 ELSE 0 END) as pickup_cnt,
                SUM(CASE WHEN status_sys = 'Created' THEN 1 ELSE 0 END) as created_cnt,
                SUM(CASE WHEN status_sys = 'Inbound' THEN orders_weight ELSE 0 END) / 1000.0 as inb_wt,
                SUM(CASE WHEN status_sys = 'Transporting' THEN orders_weight ELSE 0 END) / 1000.0 as transp_wt,
                SUM(CASE WHEN status_sys = 'Pickup Done' THEN orders_weight ELSE 0 END) / 1000.0 as pickup_wt,
                SUM(CASE WHEN status_sys = 'Created' THEN orders_weight ELSE 0 END) / 1000.0 as created_wt
            FROM enriched.dispatch_enriched
            WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date;
        ''', (d_str,))

        row = cur.fetchone()
        inb_c, tr_c, pk_c, cr_c, inb_w, tr_w, pk_w, cr_w = row
        inb_c, tr_c, pk_c, cr_c = int(inb_c or 0), int(tr_c or 0), int(pk_c or 0), int(cr_c or 0)
        inb_w, tr_w, pk_w, cr_w = round(float(inb_w or 0), 3), round(float(tr_w or 0), 3), round(float(pk_w or 0), 3), round(float(cr_w or 0), 3)

        # Rot / Backlog breakdown for this operating date
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

        kpi_summary = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "inbound_orders": inb_c,
            "inbound_weight_ton": inb_w,
            "forecast_total": tr_c + pk_c + cr_c,
            "rot_hom_truoc": rot_hom_truoc,
            "rot_hom_nay": rot_hom_nay,
            "linehaul_bn_hub": 0
        }

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

        # Save to appropriate destination directory
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

        print(f"   [{'HIST' if is_history else 'LIVE'}] Date {d_str}: Inbound={inb_c:,}, Forecast={tr_c+pk_c+cr_c:,}, Frozen={is_frozen}")

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
    print("✅ [BUILD MASTER PIPELINE v2.0] Success! All Live & History syncs complete.")
    print("============================================================")

if __name__ == '__main__':
    run_master_pipeline()
