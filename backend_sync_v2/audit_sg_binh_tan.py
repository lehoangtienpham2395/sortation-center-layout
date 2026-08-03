import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query SG BÌNH TÂN records on 2026-07-31
cur.execute('''
    SELECT 
        tracking,
        pickup_station,
        trip_code,
        dispatch_code,
        status_sys,
        operation_date_inbound
    FROM enriched.dispatch_enriched
    WHERE (pickup_station ILIKE '%%SG BÌNH TÂN%%' OR station_name ILIKE '%%SG BÌNH TÂN%%')
      AND COALESCE(op_date_inbound_effective::text, operation_date_inbound::text, operation_date_created::text) LIKE '2026-07-31%%'
      AND flag_inbound = 1;
''')

rows = cur.fetchall()

print(f"Total Inbound orders for SG BÌNH TÂN on 2026-07-31: {len(rows):,}")

trip_codes = set()
dispatch_codes = set()

for trk, pk_st, trip, disp, st_sys, op_in in rows:
    if trip:
        trip_codes.add(trip)
    if disp:
        dispatch_codes.add(disp)

print(f"\nUnique trip_code count     : {len(trip_codes)}")
print(f"Sample trip_codes           : {list(trip_codes)[:10]}")

print(f"\nUnique dispatch_code count : {len(dispatch_codes)}")
print(f"Sample dispatch_codes       : {list(dispatch_codes)[:10]}")

conn.close()
