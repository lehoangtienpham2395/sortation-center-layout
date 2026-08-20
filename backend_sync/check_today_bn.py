import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn, VALID_FILE
import pandas as pd

conn = get_pg_conn()

# Check date distribution of un-outbounded orders
df_dates = pd.read_sql("""
    SELECT 
        operation_date_created,
        COUNT(*) as total_orders,
        COUNT(CASE WHEN next_station = 'BN HUB' OR next_station LIKE 'HN %' OR next_station LIKE 'BN %' OR (dispatch_code IS NOT NULL AND (dispatch_code LIKE 'HN%' OR dispatch_code LIKE 'BN%' OR dispatch_code LIKE 'HNI%' OR dispatch_code LIKE 'BNI%')) THEN 1 END) as bn_orders
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND (status_sys IS NULL OR (status_sys NOT ILIKE '%hủy%' AND status_sys NOT ILIKE '%cancel%'))
    GROUP BY 1
    ORDER BY 1 DESC
    LIMIT 10;
""", conn)
print("--- Recent dates in enriched.dispatch_enriched ---")
print(df_dates.to_string())

conn.close()
