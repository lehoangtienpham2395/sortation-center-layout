import sys, os, time, gc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn, get_op_date, clean_ts_str
import pandas as pd

today = '2026-08-21'
conn = get_pg_conn()
print("Reading lightweight columns from PostgreSQL...")
t0 = time.time()
query = f"""
    SELECT
        tracking, status_sys, created_time,
        pickup_station, dispatch_code,
        orders_weight, pickup_time,
        next_station, round, rank,
        inbound_scandate, outbound_scandate, arrival_scandate,
        trip_code, transporing_time, transported_time,
        operation_date_created, operation_date_inbound,
        is_rebound, return_count,
        inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
        flag_pickup, op_date_pickup, op_date_inbound_effective
    FROM enriched.dispatch_enriched
    WHERE 
        (
            status_sys IS NULL 
            OR (
                status_sys NOT ILIKE '%hủy%' 
                AND status_sys NOT ILIKE '%cancel%'
                AND status_sys NOT IN ('Đã hủy', 'Cancelled', 'da huy', 'Hủy', 'Huy', 'cancel')
            )
        )
        AND (
            (
                outbound_scandate IS NULL
                AND operation_date_created::date >= ('{today}'::date - INTERVAL '15 days')
            )
            OR (
                outbound_scandate IS NOT NULL
                AND (
                    outbound_scandate::date >= '2026-08-01'
                    OR outbound_scandate_2::date >= '2026-08-01'
                )
            )
        )
    ORDER BY operation_date_created DESC, created_time DESC;
"""

df = pd.read_sql(query, conn)
conn.close()
print(f"Loaded {len(df):,} rows in {time.time() - t0:.2f}s, RAM: {df.memory_usage(deep=True).sum() / (1024*1024):.1f} MB")

t1 = time.time()
inv_group = {}
out_group = {}
backlog_group = {}
inbound_group = {}
arr_group = {}

for r in df.itertuples(index=False):
    d = r._asdict()
    sc = str(d.get('dispatch_code') or '')
    st = str(d.get('next_station') or 'BN HUB')
    pk_st = str(d.get('pickup_station') or '')
    in_status = 'Inbound'
    ref_date = str(d.get('operation_date_created') or today)[:10]
    fc_op = ref_date
    pk_op = ref_date
    ar_op = ref_date
    final_inb_hour = '10:00'
    fc_hr = '10:00:00'
    pk_hr = '10:00:00'
    ar_hr = '10:00:00'
    drop_type = ''
    trip = str(d.get('trip_code') or '')
    transp_t = ''
    transpd_t = ''
    is_reb = int(d.get('is_rebound') or 0)
    ret_cnt = int(d.get('return_count') or 0)
    wt_kg = float(d.get('orders_weight') or 0)

    key_ib = (
        st, pk_st or 'BN HUB', in_status, ref_date, fc_op, pk_op, ar_op,
        final_inb_hour, fc_hr, pk_hr, ar_hr,
        drop_type, trip, transp_t, transpd_t, is_reb
    )
    if key_ib not in inbound_group:
        inbound_group[key_ib] = [0, 0.0, ret_cnt]
    inbound_group[key_ib][0] += 1
    inbound_group[key_ib][1] += wt_kg

print(f"Aggregated {len(df):,} records into {len(inbound_group):,} keys in {time.time() - t1:.2f}s! Perfect!")
