"""
backfill_last_7_days.py — Quick 7-Day Backfill & Push Engine
============================================================
1. Fetches JFS API Dispatch, Inbound Scans, and Outbound Scans for the last 7 days.
2. Upserts & updates PostgreSQL `enriched.dispatch_enriched`.
3. Runs Master Pipeline v2.0 to update all 5 micro-JSONs for Live & History.
4. Builds & Pushes directly to GitHub main.
"""

import sys
import os
import datetime
import psycopg2
from psycopg2.extras import execute_values

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)

import pipeline_unified_v6 as pipe
from build_master_pipeline import run_master_pipeline, get_db_connection

def extract_ma10(val):
    import re
    if not val or str(val).strip() == '': return ''
    ms = re.findall(r'[A-Z]{2,3}\d{3}[A-Z0-9]', str(val))
    return ms[0] if ms else ''

def get_op_date(st_str):
    if not st_str or len(st_str) < 10: return ''
    try:
        dt = datetime.datetime.strptime(st_str[:16], '%Y-%m-%d %H:%M')
        if dt.hour < 6:
            dt = dt - datetime.timedelta(days=1)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return st_str[:10]

def run_quick_7day():
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    end_date = now_vn.date()
    start_date = end_date - datetime.timedelta(days=7)

    start_ts = f"{start_date.strftime('%Y-%m-%d')} 00:00:00"
    end_ts   = f"{end_date.strftime('%Y-%m-%d')} 23:59:59"

    print(f"============================================================")
    print(f"🚀 [QUICK 7-DAY BACKFILL] Range: {start_ts} -> {end_ts}")
    print(f"============================================================")

    session_main = pipe.build_session()
    tkn_main = pipe.TokenManager(session_main, pipe.ACCOUNT, pipe.PASSWORD, label='Quick7Day')
    token_str = tkn_main.get_token()

    if not token_str:
        print("❌ Login JFS failed! Aborting.")
        return

    dh_headers = pipe.load_json(pipe.cfg('dispatchheaders.json'))
    dh_headers['token'] = token_str

    ih_headers = pipe.load_json(pipe.cfg('inboundheaders.json'))
    ih_headers['token'] = token_str

    oh_headers = pipe.load_json(pipe.cfg('outboundheaders.json'))
    oh_headers['token'] = token_str

    ib_payload_template = pipe.load_json(pipe.cfg('inboundpayload.json'))
    ob_payload_template = pipe.load_json(pipe.cfg('outboundpayload.json'))

    i_params = {'sqlCode': ib_payload_template.get('sqlCode', 'realtime_barscan_query'), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': ih_headers.get('routeName', '')}
    o_params = {'sqlCode': ob_payload_template.get('sqlCode', 'realtime_barscan_query'), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': oh_headers.get('routeName', '')}

    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Dispatch
    dp_payload = pipe.load_json(pipe.cfg('dispatchpayload.json'))
    dp_payload['startInputTime'] = start_ts
    dp_payload['endInputTime']   = end_ts
    print(f"1. Pulling JFS Dispatch OMS (Last 7 Days)...")
    try:
        disp_recs = pipe.pull_dispatch(session_main, tkn_main, dh_headers, dp_payload, label="Disp_Quick7")
        print(f"   🟢 Dispatch: {len(disp_recs):,} records")
    except Exception as e:
        print(f"   ⚠️ Error pulling dispatch: {e}")
        disp_recs = []

    if disp_recs:
        batch = []
        for r in disp_recs:
            wb  = pipe.clean_wb(r.get('waybillId') or r.get('waybillNo'))
            ct  = str(r.get('inputTime') or r.get('dispatchNetworkTime') or '').strip()
            pt  = str(r.get('pickTime') or '').strip()
            pkn = str(r.get('pickNetworkName') or '').strip()
            pk2 = str(r.get('realPickNetworkName') or '').strip()
            stn = pipe.clean_status_sys(str(r.get('orderStatusName') or '').strip())
            dr  = str(r.get('terminalDispatchCode') or '').strip().upper()
            dc  = extract_ma10(dr) or dr
            num = int(r.get('packageNumber') or 1)
            wt  = float(r.get('packageChargeWeight') or 0.0)
            ac  = str(r.get('proxyAreaCode') or '').strip()
            ft  = str(r.get('flowTypeDesc') or '').strip()
            opd = get_op_date(ct) if ct else start_date.strftime('%Y-%m-%d')

            if wb and ct:
                batch.append((
                    wb, 'quick_7day', stn or 'Created', ct or None,
                    pkn or None, dc or None, num, wt,
                    pk2 or None, pt or None, None, ac or None, ft or None,
                    opd, 1 if pt else 0
                ))

        upsert_sql = """
            INSERT INTO enriched.dispatch_enriched (
                tracking, data_source, status_sys, created_time,
                pickup_station, dispatch_code, orders_num, orders_weight,
                pickup_station2, pickup_time, pickup_ontime, areacode, flowtypedesc,
                operation_date_created, flag_pickup
            ) VALUES %s
            ON CONFLICT (tracking) DO UPDATE SET
                status_sys               = COALESCE(NULLIF(EXCLUDED.status_sys, ''), enriched.dispatch_enriched.status_sys),
                pickup_time              = COALESCE(EXCLUDED.pickup_time, enriched.dispatch_enriched.pickup_time),
                pickup_station           = COALESCE(NULLIF(EXCLUDED.pickup_station, ''), enriched.dispatch_enriched.pickup_station),
                pickup_station2          = COALESCE(NULLIF(EXCLUDED.pickup_station2, ''), enriched.dispatch_enriched.pickup_station2),
                areacode                 = COALESCE(NULLIF(EXCLUDED.areacode, ''), enriched.dispatch_enriched.areacode),
                flowtypedesc             = COALESCE(NULLIF(EXCLUDED.flowtypedesc, ''), enriched.dispatch_enriched.flowtypedesc),
                operation_date_created   = COALESCE(EXCLUDED.operation_date_created, enriched.dispatch_enriched.operation_date_created),
                flag_pickup              = CASE WHEN EXCLUDED.pickup_time IS NOT NULL THEN 1 ELSE enriched.dispatch_enriched.flag_pickup END,
                last_updated             = CURRENT_TIMESTAMP;
        """
        try:
            execute_values(cur, upsert_sql, batch, page_size=2000)
            conn.commit()
            print(f"   🟢 PostgreSQL Dispatch: {len(batch):,} rows upserted")
        except Exception as e:
            conn.rollback()
            print(f"   ❌ DB Dispatch Error: {e}")

    # 2. Inbound Scans
    ib_payload = dict(ib_payload_template)
    ib_payload['beginDate'] = start_ts
    ib_payload['endDate']   = end_ts
    print(f"2. Pulling JFS Inbound Scans (Last 7 Days)...")
    try:
        ib_recs = pipe.pull_scan(session_main, tkn_main, ih_headers, i_params, ib_payload, label="Inbound_Quick7")
        print(f"   🟢 Inbound: {len(ib_recs):,} records")
    except Exception as e:
        print(f"   ⚠️ Error pulling inbound scans: {e}")
        ib_recs = []

    if ib_recs:
        ib_batch = [(str(r.get('scanDate') or '').strip(), get_op_date(str(r.get('scanDate') or '').strip()), pipe.clean_wb(r.get('billNo') or r.get('waybillNo'))) for r in ib_recs if r.get('billNo') or r.get('waybillNo')]
        ib_update_sql = """
            UPDATE enriched.dispatch_enriched AS d
            SET flag_inbound = 1,
                inbound_scandate = v.st::timestamptz,
                operation_date_inbound = v.op_inb,
                status_sys = CASE WHEN d.status_sys = 'Outbound' THEN 'Outbound' ELSE 'Inbound' END,
                last_updated = CURRENT_TIMESTAMP
            FROM (VALUES %s) AS v(st, op_inb, wb)
            WHERE d.tracking = v.wb;
        """
        try:
            execute_values(cur, ib_update_sql, ib_batch, page_size=2000)
            conn.commit()
            print(f"   🟢 PostgreSQL Inbound Scans: {len(ib_batch):,} updated")
        except Exception as e:
            conn.rollback()
            print(f"   ❌ DB Inbound Error: {e}")

    # 3. Outbound Scans
    ob_payload = dict(ob_payload_template)
    ob_payload['beginDate'] = start_ts
    ob_payload['endDate']   = end_ts
    print(f"3. Pulling JFS Outbound Scans (Last 7 Days)...")
    try:
        ob_recs = pipe.pull_scan(session_main, tkn_main, oh_headers, o_params, ob_payload, label="Outbound_Quick7")
        print(f"   🟢 Outbound: {len(ob_recs):,} records")
    except Exception as e:
        print(f"   ⚠️ Error pulling outbound scans: {e}")
        ob_recs = []

    if ob_recs:
        ob_batch = [(str(r.get('scanDate') or r.get('scanTime') or '').strip(), pipe.clean_wb(r.get('billNo') or r.get('waybillNo'))) for r in ob_recs if r.get('billNo') or r.get('waybillNo')]
        ob_update_sql = """
            UPDATE enriched.dispatch_enriched AS d
            SET flag_outbound = 1,
                outbound_scandate = v.st::timestamptz,
                status_sys = 'Outbound',
                last_updated = CURRENT_TIMESTAMP
            FROM (VALUES %s) AS v(st, wb)
            WHERE d.tracking = v.wb;
        """
        try:
            execute_values(cur, ob_update_sql, ob_batch, page_size=2000)
            conn.commit()
            print(f"   🟢 PostgreSQL Outbound Scans: {len(ob_batch):,} updated")
        except Exception as e:
            conn.rollback()
            print(f"   ❌ DB Outbound Error: {e}")

    conn.close()

    print(f"\n============================================================")
    print(f"🔄 Executing Master Pipeline...")
    print(f"============================================================")
    run_master_pipeline()

if __name__ == '__main__':
    run_quick_7day()
