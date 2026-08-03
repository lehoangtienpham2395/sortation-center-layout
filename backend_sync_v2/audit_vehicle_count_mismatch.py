import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Auditing REAL vehicle / trip counts for 2026-08-02 in PostgreSQL...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

# Audit Inbound orders on 2026-08-02 grouped by origin station
query = '''
    SELECT 
        CASE 
            WHEN UPPER(pickup_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'BN HUB%' THEN 'BN HUB'
            ELSE pickup_station
        END as station,
        COUNT(DISTINCT NULLIF(NULLIF(TRIM(trip_code), ''), 'NONE')) as distinct_trips,
        COUNT(DISTINCT NULLIF(NULLIF(TRIM(dispatch_code), ''), 'NONE')) as distinct_dispatches,
        COUNT(*) as order_count,
        SUM(orders_weight) as total_weight_kg
    FROM enriched.dispatch_enriched
    WHERE inbound_scandate::date = '2026-08-02'::date
       OR (status_sys = 'Inbound' AND COALESCE(operation_date_created::date, op_date_pickup::date) = '2026-08-02'::date)
    GROUP BY station
    ORDER BY order_count DESC
    LIMIT 10;
'''

df = pd.read_sql_query(query, conn)
print("=== Real Inbound Trips & Dispatches by Station (2026-08-02) ===")
print(df.to_string(index=False))

# Inspect DT SA ĐÉC and SG CỦ CHI trips/dispatches
query_detail = '''
    SELECT 
        pickup_station,
        trip_code,
        dispatch_code,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE (inbound_scandate::date = '2026-08-02'::date OR (status_sys = 'Inbound' AND COALESCE(operation_date_created::date, op_date_pickup::date) = '2026-08-02'::date))
      AND pickup_station IN ('DT SA ĐÉC', 'SG CỦ CHI', 'SG BÌNH TÂN')
    GROUP BY pickup_station, trip_code, dispatch_code
    ORDER BY pickup_station, cnt DESC
    LIMIT 20;
'''

df_detail = pd.read_sql_query(query_detail, conn)
conn.close()

print("\n=== Sample Trips & Dispatches for DT SA ĐÉC / SG CỦ CHI ===")
print(df_detail.to_string(index=False))
