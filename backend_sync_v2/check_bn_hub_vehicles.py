import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query inbound orders from BN HUB on 2026-08-01
cur.execute('''
    SELECT tracking, trip_code, orders_num, orders_weight, status_sys, pickup_station, next_station, round, rank
    FROM enriched.dispatch_enriched
    WHERE (status_sys = 'Inbound' OR inbound_scandate IS NOT NULL)
      AND COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
      AND (pickup_station ILIKE '%%BN HUB%%' OR next_station ILIKE '%%BN HUB%%' OR rank ILIKE '%%BN HUB%%');
''')

rows = cur.fetchall()
print(f"Total Inbound BN HUB records in DB today: {len(rows):,}")

unique_trips = set()
for r in rows:
    trip = r[1]
    if trip and str(trip).strip():
        unique_trips.add(str(trip).strip())

print(f"Unique trip_code (Phiếu nhiệm vụ / Mã chuyến xe) values for BN HUB: {len(unique_trips)}")
print("Trip list:", list(unique_trips))

conn.close()
