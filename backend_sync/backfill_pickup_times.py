"""
backfill_pickup_times.py — Update pickup_time & pickup_station cho cac don da co trong PostgreSQL
"""
import sys, os, time, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, 'backend_sync')
import pipeline_unified_v6 as pipe
from sync_postgre import get_pg_conn, refresh_operational_flags

tz_vn   = ZoneInfo('Asia/Ho_Chi_Minh')
now_vn  = datetime.datetime.now(tz_vn)

print("1. Kéo Dispatch data từ JFS API (7 ngày gần nhất)...")
start_str = (now_vn - datetime.timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
end_str   = now_vn.strftime('%Y-%m-%d %H:%M:%S')

session_main = pipe.build_session()
tkn_main = pipe.TokenManager(session_main, pipe.ACCOUNT, pipe.PASSWORD, label='660021')
tkn_main.get_token()

dh_headers = pipe.load_json(pipe.cfg('dispatchheaders.json'))
dp_payload = pipe.load_json(pipe.cfg('dispatchpayload.json'))
dp_payload['startInputTime'] = start_str
dp_payload['endInputTime']   = end_str

recs = pipe.pull_dispatch(session_main, tkn_main, dh_headers, dp_payload, label='DispatchBackfill')
print(f"   Lấy được {len(recs):,} đơn dispatch từ JFS API")

print("\n2. UPDATE pickup_time & pickup_station vào PostgreSQL enriched.dispatch_enriched...")
conn = get_pg_conn()
cur = conn.cursor()

from psycopg2.extras import execute_values

batch = []
for r in recs:
    wb  = pipe.clean_wb(r.get('waybillId') or r.get('waybillNo'))
    pt  = str(r.get('pickTime') or '').strip()
    pkn = str(r.get('pickNetworkName') or '').strip()
    pk2 = str(r.get('realPickNetworkName') or '').strip()
    stn = pipe.clean_status_sys(str(r.get('orderStatusName') or '').strip())
    if wb:
        batch.append((wb, stn or None, pt or None, pkn or None, pk2 or None))

update_sql = """
    UPDATE enriched.dispatch_enriched AS d SET
        pickup_time     = COALESCE(v.pickup_time::timestamptz, d.pickup_time),
        pickup_station  = COALESCE(NULLIF(v.pickup_station, ''), d.pickup_station),
        pickup_station2 = COALESCE(NULLIF(v.pickup_station2, ''), d.pickup_station2),
        status_sys      = COALESCE(NULLIF(v.status_sys, ''), d.status_sys),
        last_updated    = CURRENT_TIMESTAMP
    FROM (VALUES %s) AS v(tracking, status_sys, pickup_time, pickup_station, pickup_station2)
    WHERE d.tracking = v.tracking;
"""
execute_values(cur, update_sql, batch, page_size=2000)
conn.commit()
print(f"   Update thành công {len(batch):,} bản ghi!")

print("\n3. Chạy refresh_operational_flags() để tính lại các cờ...")
refresh_operational_flags()

cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE pickup_time IS NOT NULL")
cnt_pt = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE flag_pickup = 1")
cnt_fp = cur.fetchone()[0]

print(f"\n✅ PostgreSQL rows with pickup_time NOT NULL: {cnt_pt:,}")
print(f"✅ PostgreSQL rows with flag_pickup = 1:        {cnt_fp:,}")

if cnt_pt > 0:
    cur.execute("""
        SELECT tracking, pickup_station, pickup_time, flag_pickup, flag_inbound, flag_outbound, operation_date_created
        FROM enriched.dispatch_enriched
        WHERE pickup_time IS NOT NULL
        LIMIT 5;
    """)
    print('\nSample 5 records with pickup_time:')
    for r in cur.fetchall():
        print(f"  tracking={r[0]}  st={r[1]}  time={r[2]}  flag_pk={r[3]}  inb={r[4]}  out={r[5]}  op_cr={r[6]}")

conn.close()
print("\nBACKFILL PICKUP TIME DONE!")
