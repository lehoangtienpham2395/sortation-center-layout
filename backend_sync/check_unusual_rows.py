import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Check distinct values of all string columns in enriched.dispatch_enriched for today's forecast / active records
df = pd.read_sql("""
    SELECT 
        status_sys,
        flowtypedesc,
        round,
        rank,
        is_completed,
        is_active,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE operation_date_created::date >= '2026-08-16'
    GROUP BY 1, 2, 3, 4, 5, 6;
""", conn)
print("Distribution of status in enriched.dispatch_enriched for 2026-08-16 onwards:")
print(df.to_string())

# Check if any orders have is_active = 0 or is_completed = True or status_sys has anything unusual
df_unusual = pd.read_sql("""
    SELECT tracking, status_sys, is_active, is_completed, flowtypedesc, pickup_station, next_station
    FROM enriched.dispatch_enriched
    WHERE is_active = 0 OR is_completed = true OR status_sys ILIKE '%hủy%' OR status_sys ILIKE '%cancel%'
    LIMIT 20;
""", conn)
print("\nUnusual / Inactive / Completed rows count:", len(df_unusual))
print(df_unusual.to_string())

conn.close()
