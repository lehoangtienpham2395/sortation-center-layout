import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Auditing EVERY SINGLE TRIP & DISPATCH for DT SA ĐÉC on 2026-08-02...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

query = '''
    SELECT 
        pickup_station,
        trip_code,
        dispatch_code,
        COUNT(*) as order_count,
        SUM(orders_weight) as total_weight_kg
    FROM enriched.dispatch_enriched
    WHERE (inbound_scandate::date = '2026-08-02'::date OR (status_sys = 'Inbound' AND COALESCE(operation_date_created::date, op_date_pickup::date) = '2026-08-02'::date))
      AND UPPER(pickup_station) LIKE '%SA ĐÉC%'
    GROUP BY pickup_station, trip_code, dispatch_code
    ORDER BY order_count DESC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("=== All Trips & Dispatches for DT SA ĐÉC (2026-08-02) ===")
print(df.to_string(index=False))

print(f"\nTotal Orders for DT SA ĐÉC: {df['order_count'].sum()}")
print(f"Total Weight for DT SA ĐÉC: {df['total_weight_kg'].sum() / 1000.0:.2f} Tấn")
print(f"Total Unique trip_codes: {df['trip_code'].nunique()}")
print(f"Total Unique dispatch_codes: {df['dispatch_code'].nunique()}")
print("\nTrips with >= 50 orders:")
print(df[df['order_count'] >= 50].to_string(index=False))
