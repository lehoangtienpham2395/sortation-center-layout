import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

query = '''
    SELECT 
        pickup_station,
        COUNT(*) as order_count,
        SUM(orders_weight) / 1000.0 as weight_ton
    FROM enriched.dispatch_enriched
    WHERE is_active = 1
      AND (
          inbound_scandate::date = '2026-08-02'::date 
          OR op_date_inbound_effective::date = '2026-08-02'::date
          OR (status_sys = 'Inbound' AND operation_date_created::date = '2026-08-02'::date)
      )
    GROUP BY pickup_station
    ORDER BY order_count DESC
    LIMIT 10;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("=== Exact Inbound Orders by pickup_station in PostgreSQL (2026-08-02) ===")
print(df.to_string(index=False))
