"""
PIPELINE V2 REALTIME -- Micro-Polling Delta Engine (Unified All-Micro-JSON Sync)
Queries JFS API for recent scans in the last 60 minutes.
Upserts directly to PostgreSQL logistics_db.
Exports updated JSON payloads to ALL active JSON directories including Micro-JSONs.
"""

import sys
import os
import time
import json
import datetime
import pandas as pd
import psycopg2

sys.stdout.reconfigure(encoding='utf-8')

# Ensure backend_sync_v2 path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post, cfg, load_json, clean_wb, get_op_date,
    URL_SCAN, SCAN_PAGE_SIZE, ACCOUNT, PASSWORD
)

def run_realtime_delta_sync(minutes_back=60):
    t_start = time.time()
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    start_dt = now_vn - datetime.timedelta(minutes=minutes_back)
    
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = now_vn.strftime("%Y-%m-%d %H:%M:%S")
    
    today_str = now_vn.strftime("%Y-%m-%d")
    if now_vn.hour < 6:
        op_today = (now_vn - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        op_today = today_str

    print(f"🚀 [VER 2 REALTIME DELTA] [{now_vn.strftime('%H:%M:%S')}] Delta sync ({start_str} -> {end_str})...")

    # Connect DB
    conn = psycopg2.connect(
        dbname='logistics_db',
        user='postgres',
        password='Tien@giang0203',
        host='127.0.0.1',
        port=5433
    )
    cur = conn.cursor()

    # Login JFS
    session = build_session()
    tmgr = TokenManager(session, ACCOUNT, PASSWORD)
    token_main = tmgr.get_token()

    if not token_main:
        print("❌ Login JFS failed")
        conn.close()
        return False, 0

    headers = load_json(cfg('inboundheaders.json'))
    headers['token'] = token_main

    # Fetch recent Inbound scans
    ib_payload = load_json(cfg('inboundpayload.json'))
    ib_payload['beginDate'] = start_str
    ib_payload['endDate'] = end_str
    
    ib_params = {
        'sqlCode': ib_payload.get('sqlCode', ''),
        'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
        'routeName': headers.get('routeName', '')
    }

    print(f"   Fetching Inbound delta scans ({minutes_back}m lookback)...")
    recs = []
    page = 1
    while True:
        p = dict(ib_payload)
        p.update({'current': str(page), 'size': str(SCAN_PAGE_SIZE)})
        try:
            r = auth_post(session, URL_SCAN, tmgr, headers, params=ib_params, json_body=p, label='InboundDelta')
            dn = r.json().get('data')
            if isinstance(dn, str):
                try: dn = json.loads(dn)
                except: dn = {}
            rows = dn.get('records', []) if isinstance(dn, dict) else (dn or [])
            if not rows: break
            recs.extend(rows)
            if len(rows) < SCAN_PAGE_SIZE: break
            page += 1
        except Exception as e:
            print(f"   Inbound delta error: {e}")
            break

    print(f"   OK Inbound delta: {len(recs):,} records")

    updated_count = 0
    if recs:
        for r in recs:
            wb = clean_wb(r.get('billNo') or r.get('waybillNo'))
            st = str(r.get('scanDate') or '').strip()
            if wb and st:
                op_in = get_op_date(st)
                cur.execute('''
                    UPDATE enriched.dispatch_enriched
                    SET flag_inbound = 1,
                        inbound_scandate = %s,
                        operation_date_inbound = %s,
                        status_sys = 'Inbound',
                        last_updated = CURRENT_TIMESTAMP
                    WHERE tracking = %s;
                ''', (st, op_in, wb))
                if cur.rowcount > 0:
                    updated_count += cur.rowcount

        conn.commit()

    # Recalculate today's snapshot strictly filtering out North / Linehaul orders
    prev_date = (datetime.datetime.strptime(op_today, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    cur.execute('''
        SELECT 
            flag_inbound, flag_outbound, status_sys, pickup_station, next_station, rank, round,
            COALESCE(op_date_pickup::text, operation_date_created::text) AS ref_date
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= %s::date;
    ''', (op_today,))

    rows = cur.fetchall()

    rot_hom_truoc = 0
    rot_hom_nay = 0
    rot_ton_dong = 0

    for flag_in, flag_out, st_sys, pk_st, next_st, rk, rd, ref_d in rows:
        stn = str(st_sys or '').strip()
        is_canceled = (stn == 'Đã hủy')
        pk_st_u = str(pk_st or '').upper()
        next_st_u = str(next_st or '').upper()
        rk_u = str(rk or '').upper()
        rd_u = str(rd or '').upper()

        is_north = ('BN HUB' in pk_st_u or 'BN HUB' in next_st_u or 'BN HUB' in rk_u or 'LINEHAUL' in rd_u or pk_st_u.startswith(('HN ', 'HD ', 'HY ')))
        is_rot = (not flag_in) and (not flag_out) and (not is_canceled) and (not is_north)

        if is_rot and ref_d:
            ref_d_str = str(ref_d)[:10]
            if ref_d_str == op_today:
                rot_hom_nay += 1
            elif ref_d_str == prev_date:
                rot_hom_truoc += 1
            elif ref_d_str < prev_date:
                rot_ton_dong += 1

    # Update daily_kpi_snapshot
    cur.execute('''
        INSERT INTO enriched.daily_kpi_snapshot (op_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (op_date) DO UPDATE SET
            rot_hom_truoc = EXCLUDED.rot_hom_truoc,
            rot_hom_nay   = EXCLUDED.rot_hom_nay,
            rot_ton_dong  = EXCLUDED.rot_ton_dong,
            updated_at    = CURRENT_TIMESTAMP;
    ''', (op_today, rot_hom_truoc, rot_hom_nay, rot_ton_dong))

    conn.commit()

    # Query active records for today & yesterday to update json payloads
    cur.execute('''
        SELECT 
            tracking, status_sys, created_time, pickup_station, orders_num, orders_weight,
            inbound_scandate, outbound_scandate, operation_date_created, operation_date_inbound,
            op_date_pickup, rank, round, next_station
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) >= %s::date;
    ''', (prev_date,))

    inb_rows = cur.fetchall()

    json_records = []
    inbound_orders_count = 0
    inbound_weight_ton = 0.0

    for trk, st_sys, cr_tm, pk_st, ord_n, ord_w, in_dt, out_dt, op_cr, op_in, op_pk, rk, rd, next_st in inb_rows:
        status_norm = 'Inbound' if (st_sys == 'Inbound' or in_dt is not None) else (st_sys or 'Created')
        if status_norm == 'Inbound':
            inbound_orders_count += int(ord_n or 1)
            inbound_weight_ton += float(ord_w or 0.0)

        json_records.append({
            'tracking': trk,
            'status': status_norm,
            'status_sys': st_sys,
            'Created_time': str(cr_tm or ''),
            'pickup_station': pk_st or '',
            'station_name': next_st or '',
            'volume': ord_n or 1,
            'weight_ton': float(ord_w or 0.0),
            'op_date_forecast': str(op_pk or op_cr or '')[:10],
            'op_date_inbound': str(op_in or '')[:10],
            'inbound_scandate': str(in_dt or ''),
            'outbound_scandate': str(out_dt or ''),
            'rank': rk or '',
            'round': rd or ''
        })

    timestamp_str = now_vn.strftime("%H:%M:%S %d/%m/%Y")
    
    # Unified last_update object
    # Preserve existing daily_snapshots from current last_update.json to avoid
    # clobbering historical (flag-based) daily snapshots.
    merged_snapshots = {}
    for target_dir in [
        os.path.join(ROOT_DIR, "public", "data"),
        os.path.join(ROOT_DIR, "data")
    ]:
        existing_lu_path = os.path.join(target_dir, "last_update.json")
        if os.path.exists(existing_lu_path):
            try:
                with open(existing_lu_path, 'r', encoding='utf-8') as f:
                    existing_lu = json.load(f)
                merged_snapshots = existing_lu.get("daily_snapshots", {})
                break
            except (IOError, json.JSONDecodeError, AttributeError):
                merged_snapshots = {}
    merged_snapshots[op_today] = {
        "rot_hom_truoc": rot_hom_truoc,
        "rot_hom_nay": rot_hom_nay,
        "rot_ton_dong": rot_ton_dong,
        "is_frozen": False
    }

    lu = {
        "last_update": timestamp_str,
        "rot_hom_truoc": rot_hom_truoc,
        "rot_hom_nay": rot_hom_nay,
        "total_records": len(json_records),
        "daily_snapshots": merged_snapshots,
        "contract_version": "2.0.0"
    }

    # Micro-JSON inbound_kpi_summary.json payload
    kpi_summary = {
        "op_date": op_today,
        "contract_version": "2.0.0",
        "inbound_orders": inbound_orders_count,
        "inbound_weight_ton": round(inbound_weight_ton, 3),
        "forecast_total": rot_hom_truoc + rot_hom_nay,
        "rot_hom_truoc": rot_hom_truoc,
        "rot_hom_nay": rot_hom_nay,
        "rot_ton_dong": rot_ton_dong,
        "linehaul_bn_hub": 0
    }

    # Write to ALL 3 directory locations and all sub-micro-JSON paths
    json_targets = [
        os.path.join(ROOT_DIR, "public", "data"),
        os.path.join(ROOT_DIR, "data"),
        os.path.join(ROOT_DIR, "src", "data")
    ]

    for target_dir in json_targets:
        os.makedirs(target_dir, exist_ok=True)
        
        # Save inbound.json
        with open(os.path.join(target_dir, "inbound.json"), 'w', encoding='utf-8') as f:
            json.dump(json_records, f, ensure_ascii=False)
            
        # Save last_update.json
        with open(os.path.join(target_dir, "last_update.json"), 'w', encoding='utf-8') as f:
            json.dump(lu, f, ensure_ascii=False, indent=2)

        # Save inbound_kpi_summary.json
        with open(os.path.join(target_dir, "inbound_kpi_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(kpi_summary, f, ensure_ascii=False, indent=2)

        # Save live/inbound_kpi_summary.json
        live_dir = os.path.join(target_dir, "live")
        os.makedirs(live_dir, exist_ok=True)
        with open(os.path.join(live_dir, "inbound_kpi_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(kpi_summary, f, ensure_ascii=False, indent=2)

        # Save history/op_today/inbound_kpi_summary.json
        hist_today_dir = os.path.join(target_dir, "history", op_today)
        os.makedirs(hist_today_dir, exist_ok=True)
        with open(os.path.join(hist_today_dir, "inbound_kpi_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(kpi_summary, f, ensure_ascii=False, indent=2)

    conn.close()

    elapsed = time.time() - t_start
    print(f"✅ [VER 2 REALTIME DELTA] Done in {elapsed:.2f}s | Updated ALL micro-JSONs ({len(json_records):,} records) | Timestamp: {timestamp_str} | Today Rớt hôm trước: {rot_hom_truoc}, Rớt hôm nay: {rot_hom_nay}, Total Forecast: {rot_hom_truoc + rot_hom_nay}")
    return True, updated_count

if __name__ == "__main__":
    run_realtime_delta_sync(60)
