"""
PIPELINE V2 REALTIME -- Micro-Polling Delta Engine
Queries JFS API for recent scans in the last 15 minutes.
Upserts directly to PostgreSQL logistics_db.
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
sys.path.insert(0, BASE_DIR)

from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post, cfg, load_json, clean_wb, get_op_date,
    URL_SCAN, SCAN_PAGE_SIZE, ACCOUNT, PASSWORD
)

def run_realtime_delta_sync(minutes_back=15):
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

    print("   Fetching Inbound delta scans...")
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

    # Recalculate today's snapshot
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
    conn.close()

    # Update public/data/last_update.json
    ROOT_DIR = os.path.dirname(BASE_DIR)
    last_update_path = os.path.join(ROOT_DIR, "public", "data", "last_update.json")
    if os.path.exists(last_update_path):
        with open(last_update_path, 'r', encoding='utf-8') as f:
            lu = json.load(f)
    else:
        lu = {}

    lu["last_update"] = now_vn.strftime("%H:%M:%S %d/%m/%Y")
    lu["rot_hom_truoc"] = rot_hom_truoc
    lu["rot_hom_nay"] = rot_hom_nay

    daily_snaps = lu.get("daily_snapshots", {})
    daily_snaps[op_today] = {
        "rot_hom_truoc": rot_hom_truoc,
        "rot_hom_nay": rot_hom_nay,
        "rot_ton_dong": rot_ton_dong,
        "is_frozen": False
    }
    lu["daily_snapshots"] = daily_snaps

    with open(last_update_path, 'w', encoding='utf-8') as f:
        json.dump(lu, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t_start
    print(f"✅ [VER 2 REALTIME DELTA] Done in {elapsed:.2f}s | Updated DB rows: {updated_count} | Today Rớt hôm trước: {rot_hom_truoc}, Rớt hôm nay: {rot_hom_nay}")
    return True, updated_count

if __name__ == "__main__":
    run_realtime_delta_sync(15)
