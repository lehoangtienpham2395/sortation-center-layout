import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)

# 1. Inspect ALL flags and timestamps for orders created on 2026-08-03 and 2026-08-02
query = '''
    SELECT 
        status_sys,
        flag_inbound,
        flag_outbound,
        (inbound_scandate IS NOT NULL) as has_inbound_scan,
        (outbound_scandate IS NOT NULL) as has_outbound_scan,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE COALESCE(operation_date_created::date, op_date_pickup::date) IN ('2026-08-03'::date, '2026-08-02'::date)
    GROUP BY status_sys, flag_inbound, flag_outbound, has_inbound_scan, has_outbound_scan
    ORDER BY cnt DESC;
'''

df = pd.read_sql_query(query, conn)
print("=== All Dispatch Orders Status & Scan Flags Breakdown (2026-08-02 & 2026-08-03) ===")
print(df.to_string(index=False))

# 2. Query STRICT TRULY UN-INBOUNDED AND UN-OUTBOUNDED ORDERS ONLY
strict_query = '''
    SELECT 
        COALESCE(operation_date_created::date, op_date_pickup::date)::text as date_created,
        CASE 
            WHEN UPPER(rank) = 'LINEHAUL' OR UPPER(next_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'HN %' OR UPPER(next_station) LIKE 'HD %' OR UPPER(next_station) LIKE 'HY %' OR UPPER(pickup_station) LIKE 'BN HUB%' THEN 'Linehaul'
            ELSE 'Shuttle'
        END as route_type,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound', 'Canceled', 'Đã nhập kho', 'Đã xuất kho', 'Đã hủy')
      AND inbound_scandate IS NULL 
      AND outbound_scandate IS NULL
      AND (flag_inbound = 0 OR flag_inbound IS NULL)
      AND (flag_outbound = 0 OR flag_outbound IS NULL)
    GROUP BY date_created, route_type
    ORDER BY date_created DESC;
'''

strict_df = pd.read_sql_query(strict_query, conn)
conn.close()

print("\n=== STRICT TRULY UN-INBOUNDED & UN-OUTBOUNDED ORDERS ONLY ===")
print(strict_df.to_string(index=False))
