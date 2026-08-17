import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

df_bn_sample = pd.read_sql("""
    SELECT 
        tracking,
        status_sys,
        pickup_station,
        next_station,
        operation_date_created,
        inbound_scandate,
        outbound_scandate,
        flag_pickup,
        flag_inbound,
        flag_outbound
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND (next_station LIKE '%BN HUB%' OR next_station LIKE 'HN %')
      AND operation_date_created::date < '2026-08-17'
    LIMIT 20;
""", conn)
print("Sample BN HUB older orders:")
print(df_bn_sample.to_string())

conn.close()
