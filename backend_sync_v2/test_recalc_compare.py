import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Get column names
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='enriched' AND table_name='dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]

cur.execute('''
    SELECT *
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= '2026-08-01'::date;
''')

rows = cur.fetchall()

col_idx_ref = cols.index('op_date_pickup') if 'op_date_pickup' in cols else cols.index('operation_date_created')
col_idx_created = cols.index('operation_date_created')
col_idx_flag_in = cols.index('flag_inbound')
col_idx_flag_out = cols.index('flag_outbound')
col_idx_status = cols.index('status_sys')
col_idx_pk = cols.index('pickup_station')
col_idx_next = cols.index('next_station')
col_idx_rank = cols.index('rank')
col_idx_round = cols.index('round')

target_date = '2026-08-01'
prev_date = '2026-07-31'

rot_r1_truoc = 0
rot_r1_nay = 0

for row in rows:
    ref_d = row[col_idx_ref] or row[col_idx_created]
    has_in = row[col_idx_flag_in]
    has_out = row[col_idx_flag_out]
    st_sys = str(row[col_idx_status] or '').strip()
    pk_st = str(row[col_idx_pk] or '').strip().upper()
    next_st = str(row[col_idx_next] or '').strip().upper()
    rk = str(row[col_idx_rank] or '').strip().upper()
    rd = str(row[col_idx_round] or '').strip().upper()
    
    is_canceled = (st_sys == 'Đã hủy')
    is_north = ('BN HUB' in pk_st or 'BN HUB' in next_st or 'BN HUB' in rk or 'LINEHAUL' in rd or pk_st.startswith(('HN ', 'HD ', 'HY ')))
    is_rot = (not has_in) and (not has_out) and (not is_canceled) and (not is_north)
    
    if is_rot and ref_d:
        ref_d_str = str(ref_d)[:10]
        if ref_d_str == target_date:
            rot_r1_nay += 1
        elif ref_d_str == prev_date:
            rot_r1_truoc += 1

print(f"Recalc method result for 2026-08-01 -> Rớt trước: {rot_r1_truoc}, Rớt nay: {rot_r1_nay}")

# Now check pipeline_v2_realtime query
cur.execute('''
    SELECT 
        flag_inbound, flag_outbound, status_sys, pickup_station, next_station, rank, round,
        COALESCE(op_date_pickup::text, operation_date_created::text) AS ref_date
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= '2026-08-01'::date;
''')

rows_v2 = cur.fetchall()

v2_truoc = 0
v2_nay = 0

for flag_in, flag_out, st_sys, pk_st, next_st, rk, rd, ref_d in rows_v2:
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
        if ref_d_str == target_date:
            v2_nay += 1
        elif ref_d_str == prev_date:
            v2_truoc += 1

print(f"Pipeline V2 query result -> Rớt trước: {v2_truoc}, Rớt nay: {v2_nay}")

conn.close()
