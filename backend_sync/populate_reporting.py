import sys, os, datetime, warnings
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), 'backend_sync'))
sys.path.insert(0, 'backend_sync')
import pandas as pd
from sync_postgre import get_pg_conn, get_op_date, clean_ts_str, VALID_FILE
from zoneinfo import ZoneInfo
from collections import defaultdict

tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
now_vn = datetime.datetime.now(tz_vn)
today_str = now_vn.strftime('%Y-%m-%d')

def load_valid():
    dz, da, ds = {}, {}, {}
    if not os.path.exists(VALID_FILE): return dz, da, ds
    dv = pd.read_csv(VALID_FILE, dtype=str); dv.columns = dv.columns.str.strip()
    sc = next((c for c in ['sortcode','Ma tram','Dispatch_code'] if c in dv.columns), None)
    ac = next((c for c in ['area','AreaID'] if c in dv.columns), None)
    sc_col = next((c for c in ['Buu cuc','Station_1','Station_2'] if c in dv.columns), None)
    zc = next((c for c in ['Zone','Hubcode'] if c in dv.columns), None)
    if sc and ac:
        k = dv[sc].dropna().str.strip().str.upper()
        if zc: dz = dict(zip(k, dv[zc].fillna('3').str.strip()))
        da = dict(zip(k, dv[ac].fillna('C01').str.strip()))
        if sc_col: ds = dict(zip(k, dv[sc_col].fillna('').str.strip()))
    return dz, da, ds

ZONE_MAP = {'SR0001':'1','BNI001':'1','1':'1','2':'2','3':'3'}
dict_zone, dict_area, dict_station = load_valid()

# --- Connect psycopg2 ---
conn = get_pg_conn()
conn.autocommit = False
cur = conn.cursor()

# Query du lieu 14 ngay
print("Querying enriched.dispatch_enriched (14 ngay)...")
cur.execute("""
    SELECT tracking, dispatch_code, next_station, orders_weight,
           created_time, pickup_time, inbound_scandate, outbound_scandate,
           arrival_scandate, transporing_time, trip_code,
           is_rebound, return_count, is_backlog, status_sys,
           operation_date_created, operation_date_inbound,
           inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
           flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound,
           op_date_pickup, op_date_inbound_effective
    FROM enriched.dispatch_enriched
    WHERE operation_date_created >= CURRENT_DATE - 14
       OR operation_date_inbound >= CURRENT_DATE - 14
       OR operation_date_inbound_2 >= CURRENT_DATE - 14
""")
cols = [d[0] for d in cur.description]
rows_raw = cur.fetchall()
df = pd.DataFrame(rows_raw, columns=cols).fillna('')
print(f"  {len(df):,} rows loaded")

# Collect op_dates
op_dates = set()
for v in df['operation_date_inbound'].astype(str):
    if v and v != 'None' and len(v) >= 10: op_dates.add(v[:10])
for v in df['operation_date_created'].astype(str):
    if v and v != 'None' and len(v) >= 10: op_dates.add(v[:10])
for v in df['operation_date_inbound_2'].astype(str):
    if v and v != 'None' and len(v) >= 10: op_dates.add(v[:10])
op_dates = sorted([d for d in op_dates if d >= '2026-07-14'], reverse=True)
print(f"  Backfill {len(op_dates)} ngay: {op_dates}\n")

for op_date_str in op_dates:
    mask = (
        (df['operation_date_inbound'].astype(str).str[:10] == op_date_str) |
        (df['operation_date_created'].astype(str).str[:10] == op_date_str) |
        (df['operation_date_inbound_2'].astype(str).str[:10] == op_date_str)
    )
    df_day = df[mask]
    record_type = 'rolling' if op_date_str == today_str else 'snapshot'

    kpi = dict(ti=0, to=0, tp=0, tc=0, tr=0, rrt=0, rrn=0, tb=0, wti=0.0, wto=0.0)
    hm = {f"{h:02d}:00": 0 for h in range(24)}
    ib_agg  = defaultdict(lambda: [0, 0.0])
    out_agg = defaultdict(lambda: [0, 0.0, 780])
    inv_agg = defaultdict(lambda: [0, 0.0, 780])

    for _, r in df_day.iterrows():
        sc_raw  = str(r.get('dispatch_code','') or '').strip().upper()
        next_st = str(r.get('next_station','') or '').strip()
        station = dict_station.get(sc_raw,'') or (next_st if next_st else 'KHONG VUNG KHAC')
        zone    = ZONE_MAP.get(dict_zone.get(sc_raw,'3'), '3')
        area_id = dict_area.get(sc_raw, 'C01')
        cap     = 1400 if area_id == 'A06' else 780
        wt_ton  = round(float(r.get('orders_weight') or 0) / 1000, 4)

        cr_t   = clean_ts_str(r.get('created_time'))
        pk_t   = clean_ts_str(r.get('pickup_time'))
        inb_t  = clean_ts_str(r.get('inbound_scandate'))
        outb_t = clean_ts_str(r.get('outbound_scandate'))
        arr_t  = clean_ts_str(r.get('arrival_scandate'))
        trip   = str(r.get('trip_code','') or '').strip()
        is_reb = int(r.get('is_rebound') or 0)
        ret_c  = int(r.get('return_count') or 0)
        inb_t2 = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t2= clean_ts_str(r.get('outbound_scandate_2'))
        op_inb2= str(r.get('operation_date_inbound_2') or '')[:10]

        has_in  = int(r.get('flag_inbound') or 0) == 1
        has_out = int(r.get('flag_outbound') or 0) == 1
        has_arr = int(r.get('flag_arrival') or 0) == 1
        has_pick= int(r.get('flag_pickup') or 0) == 1

        op_inb  = str(r.get('op_date_inbound_effective') or r.get('operation_date_inbound') or '')[:10]
        op_pick = str(r.get('op_date_pickup') or '')[:10] or get_op_date(pk_t)
        op_arr  = get_op_date(arr_t)
        op_fc   = get_op_date(cr_t)
        op_outb = get_op_date(outb_t)

        fin_op_inb  = op_inb2 if (is_reb and op_inb2) else (op_inb if inb_t else None)
        fin_hr      = inb_t2[11:13] if (is_reb and len(inb_t2)>=13) else (inb_t[11:13] if len(inb_t)>=13 else None)
        fin_hslot   = f"{fin_hr}:00" if fin_hr else None

        if has_in or (is_reb and inb_t2): kpi['ti']+=1; kpi['wti']+=wt_ton
        if has_out or outb_t2:            kpi['to']+=1; kpi['wto']+=wt_ton
        if has_pick:                      kpi['tp']+=1
        if not has_pick:                  kpi['tc']+=1
        if is_reb:                        kpi['tr']+=1
        if has_in and not has_out:        kpi['tb']+=1

        stn_raw = str(r.get('status_sys', '')).strip()
        is_canceled = (stn_raw == 'Đã hủy')
        op_cr_date = str(r.get('operation_date_created') or '')[:10] or op_fc
        drop_type = ''
        if not has_in and not bool(arr_t) and not is_canceled:
            if op_cr_date == op_date_str:   drop_type='rot_today'; kpi['rrn']+=1
            elif op_cr_date and op_cr_date < op_date_str: drop_type='rot_yesterday'; kpi['rrt']+=1

        status = ('Inbound' if (has_in or is_reb) else
                  'Transporting' if bool(arr_t) else
                  'Pickup Done' if has_pick else 'Created')

        k_ib = (op_date_str, station, status,
                fin_op_inb, op_fc or None, op_pick or None, op_arr or None,
                fin_hslot, drop_type or None, trip or None, is_reb, ret_c, record_type)
        ib_agg[k_ib][0] += 1; ib_agg[k_ib][1] += wt_ton

        if has_out and op_outb == op_date_str:
            k_out = (op_date_str, zone, area_id, station, cap, record_type)
            out_agg[k_out][0]+=1; out_agg[k_out][1]+=wt_ton; out_agg[k_out][2]=cap

        if has_in and not has_out and not is_reb:
            k_inv = (op_date_str, zone, area_id, station, cap, record_type)
            inv_agg[k_inv][0]+=1; inv_agg[k_inv][1]+=wt_ton; inv_agg[k_inv][2]=cap

        if fin_hslot and fin_op_inb == op_date_str and fin_hslot in hm:
            hm[fin_hslot] += 1

    # --- DELETE + INSERT ---
    cur.execute("DELETE FROM reporting.inbound_daily  WHERE op_date=%s AND record_type=%s", (op_date_str,record_type))
    cur.execute("DELETE FROM reporting.outbound_daily WHERE op_date=%s AND record_type=%s", (op_date_str,record_type))
    cur.execute("DELETE FROM reporting.inventory_daily WHERE op_date=%s AND record_type=%s",(op_date_str,record_type))
    cur.execute("DELETE FROM reporting.heatmap_daily  WHERE op_date=%s AND record_type=%s", (op_date_str,record_type))

    for k,(vol,wt) in ib_agg.items():
        cur.execute("""INSERT INTO reporting.inbound_daily
            (op_date,station_name,status,volume,weight_ton,op_date_inbound,op_date_forecast,op_date_pickup,op_date_arrival,inbound_hour,drop_type,trip_code,is_rebound,return_count,record_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (k[0],k[1],k[2],vol,round(wt,4),k[3],k[4],k[5],k[6],k[7],k[8],k[9],k[10],k[11],k[12]))
    for k,(vol,wt,cap) in out_agg.items():
        cur.execute("INSERT INTO reporting.outbound_daily (op_date,zone,area_id,station_name,volume,weight_ton,capacity,record_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (k[0],k[1],k[2],k[3],vol,round(wt,4),cap,k[5]))
    for k,(vol,wt,cap) in inv_agg.items():
        cur.execute("INSERT INTO reporting.inventory_daily (op_date,zone,area_id,station_name,volume,weight_ton,capacity,record_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (k[0],k[1],k[2],k[3],vol,round(wt,4),cap,k[5]))
    for hs,vol in hm.items():
        cur.execute("INSERT INTO reporting.heatmap_daily (op_date,hour_slot,volume,record_type) VALUES (%s,%s,%s,%s) ON CONFLICT (op_date,hour_slot) DO UPDATE SET volume=EXCLUDED.volume,record_type=EXCLUDED.record_type,refreshed_at=NOW()",
            (op_date_str,hs,vol,record_type))

    rate = round(kpi['to']/kpi['ti']*100,2) if kpi['ti']>0 else 0
    cur.execute("""INSERT INTO reporting.kpi_daily
        (op_date,total_inbound,total_outbound,total_pickup,total_created,total_rebound,rot_hom_truoc,rot_hom_nay,total_backlog,inbound_weight_ton,outbound_weight_ton,outbound_rate,record_type,snapped_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (op_date) DO UPDATE SET total_inbound=EXCLUDED.total_inbound,total_outbound=EXCLUDED.total_outbound,total_pickup=EXCLUDED.total_pickup,total_created=EXCLUDED.total_created,total_rebound=EXCLUDED.total_rebound,rot_hom_truoc=EXCLUDED.rot_hom_truoc,rot_hom_nay=EXCLUDED.rot_hom_nay,total_backlog=EXCLUDED.total_backlog,inbound_weight_ton=EXCLUDED.inbound_weight_ton,outbound_weight_ton=EXCLUDED.outbound_weight_ton,outbound_rate=EXCLUDED.outbound_rate,record_type=EXCLUDED.record_type,snapped_at=NOW()""",
        (op_date_str,kpi['ti'],kpi['to'],kpi['tp'],kpi['tc'],kpi['tr'],kpi['rrt'],kpi['rrn'],kpi['tb'],round(kpi['wti'],4),round(kpi['wto'],4),rate,record_type))
    conn.commit()
    print(f"  {op_date_str} [{record_type:8s}] inbound={kpi['ti']:,} outbound={kpi['to']:,} backlog={kpi['tb']:,} rot_truoc={kpi['rrt']} rot_nay={kpi['rrn']} rate={rate}%")

# Verify
cur.execute("SELECT op_date,total_inbound,total_outbound,total_backlog,rot_hom_truoc,rot_hom_nay,outbound_rate,record_type FROM reporting.kpi_daily ORDER BY op_date DESC LIMIT 10")
print("\nKPI_DAILY:")
print(f"  {'op_date':<12} {'inbound':>8} {'outbound':>9} {'backlog':>8} {'rot_T':>6} {'rot_H':>6} {'rate%':>6} type")
for r in cur.fetchall():
    print(f"  {str(r[0]):<12} {r[1]:>8,} {r[2]:>9,} {r[3]:>8,} {r[4]:>6} {r[5]:>6} {float(r[6]):>6.1f} {r[7]}")

conn.close()
print("\nDONE!")
