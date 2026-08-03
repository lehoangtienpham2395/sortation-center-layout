"""
backfill_full_july_august.py — Full Historical Data Backfill Engine (01/07/2026 to Present + 7-day lookback from 24/06/2026)
====================================================================================================================
1. Pulls JFS Dispatch API daily from 2026-06-24 to 2026-08-03.
2. Upserts directly to PostgreSQL logistics_db (`enriched.dispatch_enriched`).
3. Refreshes operational flags & calculates historical date snapshots.
4. Runs `build_master_pipeline.py` to produce all frozen history snapshots (data/history/YYYY-MM-DD/).
"""

import sys
import os
import time
import datetime
import json
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

def run_backfill_full_july():
    # 7-day lookback from 01/07/2026 means start at 2026-06-24
    start_date = datetime.date(2026, 6, 24)
    now_vn = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    end_date = now_vn.date()

    dates = []
    curr = start_date
    while curr <= end_date:
        dates.append(curr.strftime('%Y-%m-%d'))
        curr += datetime.timedelta(days=1)

    print(f"============================================================")
    print(f"🚀 [BACKFILL FULL JULY & AUGUST] Range: {dates[0]} -> {dates[-1]} ({len(dates)} days)")
    print(f"============================================================")

    session_main = pipe.build_session()
    tkn_main = pipe.TokenManager(session_main, pipe.ACCOUNT, pipe.PASSWORD, label='BackfillJuly')
    token_str = tkn_main.get_token()

    if not token_str:
        print("❌ Login JFS failed! Aborting backfill.")
        return

    dh_headers = pipe.load_json(pipe.cfg('dispatchheaders.json'))
    dh_headers['token'] = token_str

    conn = get_db_connection()
    cur = conn.cursor()

    for d_str in dates:
        print(f"\n📅 Fetching JFS Dispatch for date: {d_str} (00:00:00 -> 23:59:59)...")
        dp_payload = pipe.load_json(pipe.cfg('dispatchpayload.json'))
        dp_payload['startInputTime'] = f"{d_str} 00:00:00"
        dp_payload['endInputTime']   = f"{d_str} 23:59:59"

        try:
            recs = pipe.pull_dispatch(session_main, tkn_main, dh_headers, dp_payload, label=f"Dispatch_{d_str}")
            print(f"   🟢 Received {len(recs):,} dispatch records for {d_str}")
        except Exception as e:
            print(f"   ⚠️ Error pulling dispatch for {d_str}: {e}")
            recs = []

        if recs:
            batch = []
            for r in recs:
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

                if wb and ct:
                    batch.append((
                        wb, 'backfill_v2', stn or 'Created', ct or None,
                        pkn or None, dc or None, num, wt,
                        pk2 or None, pt or None, None, ac or None, ft or None,
                        d_str
                    ))

            upsert_sql = """
                INSERT INTO enriched.dispatch_enriched (
                    tracking, data_source, status_sys, created_time,
                    pickup_station, dispatch_code, orders_num, orders_weight,
                    pickup_station2, pickup_time, pickup_ontime, areacode, flowtypedesc,
                    operation_date_created
                ) VALUES %s
                ON CONFLICT (tracking) DO UPDATE SET
                    status_sys               = COALESCE(NULLIF(EXCLUDED.status_sys, ''), enriched.dispatch_enriched.status_sys),
                    pickup_time              = COALESCE(EXCLUDED.pickup_time, enriched.dispatch_enriched.pickup_time),
                    pickup_station           = COALESCE(NULLIF(EXCLUDED.pickup_station, ''), enriched.dispatch_enriched.pickup_station),
                    pickup_station2          = COALESCE(NULLIF(EXCLUDED.pickup_station2, ''), enriched.dispatch_enriched.pickup_station2),
                    areacode                 = COALESCE(NULLIF(EXCLUDED.areacode, ''), enriched.dispatch_enriched.areacode),
                    flowtypedesc             = COALESCE(NULLIF(EXCLUDED.flowtypedesc, ''), enriched.dispatch_enriched.flowtypedesc),
                    operation_date_created   = COALESCE(EXCLUDED.operation_date_created, enriched.dispatch_enriched.operation_date_created),
                    last_updated             = CURRENT_TIMESTAMP;
            """
            try:
                execute_values(cur, upsert_sql, batch, page_size=2000)
                conn.commit()
                print(f"   🟢 Upserted {len(batch):,} rows to PostgreSQL for {d_str}")
            except Exception as e:
                conn.rollback()
                print(f"   ❌ DB Upsert Error for {d_str}: {e}")

    conn.close()

    print(f"\n============================================================")
    print(f"🔄 Executing Master Pipeline to generate full historical snapshots...")
    print(f"============================================================")
    run_master_pipeline()

if __name__ == '__main__':
    run_backfill_full_july()
