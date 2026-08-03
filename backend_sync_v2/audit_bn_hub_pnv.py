import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query all Inbound records where pickup_station / station_name = 'BN HUB'
cur.execute('''
    SELECT 
        tracking,
        pickup_station,
        next_station,
        rank,
        round,
        trip_code,
        orders_num,
        orders_weight,
        inbound_scandate
    FROM enriched.dispatch_enriched
    WHERE (status_sys = 'Inbound' OR inbound_scandate IS NOT NULL)
      AND COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date;
''')

rows = cur.fetchall()

bn_hub_records = []
for r in rows:
    trk, pk_st, next_st, rk, rd, trip, ord_n, ord_w, in_dt = r
    pk_u = str(pk_st or '').strip().upper()
    next_u = str(next_st or '').strip().upper()
    rk_u = str(rk or '').strip().upper()
    
    # Check if station name evaluates to BN HUB in frontend
    fc_name = pk_st or next_st or rk or ''
    if 'BN HUB' in str(fc_name).upper():
        bn_hub_records.append((trk, trip, ord_n, ord_w, pk_st, next_st, rk, rd))

print(f"Total Inbound BN HUB records for 2026-08-01: {len(bn_hub_records)}")

trip_map = {}
for trk, trip, ord_n, ord_w, pk_st, next_st, rk, rd in bn_hub_records:
    t_str = str(trip or 'NO_TRIP_CODE').strip()
    if t_str not in trip_map:
        trip_map[t_str] = {'count': 0, 'weight': 0.0, 'samples': []}
    trip_map[t_str]['count'] += int(ord_n or 1)
    trip_map[t_str]['weight'] += float(ord_w or 0.0)
    if len(trip_map[t_str]['samples']) < 3:
        trip_map[t_str]['samples'].append(trk)

print(f"\nBreakdown by trip_code (Phiếu nhiệm vụ / Mã chuyến xe): {len(trip_map)} unique trips")
for t_code, info in trip_map.items():
    print(f"  - Trip Code: '{t_code}' -> Parcels: {info['count']:,}, Weight: {info['weight']:.2f} kg, Sample trackings: {info['samples']}")

conn.close()
