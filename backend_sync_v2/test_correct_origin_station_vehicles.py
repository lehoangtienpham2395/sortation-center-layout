import psycopg2
import pandas as pd
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Calculating ACCURATE Vehicle Counts per Station for 2026-08-02...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

# Query exact inbound metrics and real distinct trip_code count per station for 2026-08-02
query = '''
    WITH station_trips AS (
        SELECT 
            CASE 
                WHEN UPPER(pickup_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'BN HUB%' OR UPPER(rank) = 'LINEHAUL' THEN 'BN HUB'
                ELSE pickup_station
            END as station,
            trip_code,
            COUNT(*) as trip_orders,
            SUM(orders_weight) as trip_weight
        FROM enriched.dispatch_enriched
        WHERE (inbound_scandate::date = '2026-08-02'::date OR status_sys = 'Inbound' AND COALESCE(operation_date_created::date, op_date_pickup::date) = '2026-08-02'::date)
        GROUP BY station, trip_code
    )
    SELECT 
        station,
        SUM(trip_orders) as total_orders,
        ROUND(SUM(trip_weight)/1000.0, 1) as total_weight_ton,
        COUNT(DISTINCT CASE WHEN trip_orders >= 15 THEN trip_code END) as main_trips_15,
        COUNT(DISTINCT CASE WHEN trip_orders >= 20 THEN trip_code END) as main_trips_20,
        COUNT(DISTINCT trip_code) as total_raw_trips
    FROM station_trips
    WHERE station IS NOT NULL AND station != ''
    GROUP BY station
    ORDER BY total_orders DESC
    LIMIT 10;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("=== ACCURATE VEHICLE COUNTS AUDIT (2026-08-02) ===")
print(df.to_string(index=False))
