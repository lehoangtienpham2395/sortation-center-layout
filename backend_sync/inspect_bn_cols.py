import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

df_bn = pd.read_sql("""
    SELECT *
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND (next_station = 'BN HUB' OR next_station LIKE 'HN %' OR next_station LIKE 'BN %')
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

print("BN HUB DataFrame shape:", df_bn.shape)
print("\nUnique values in key columns:")
for col in ['data_source', 'pickup_ontime', 'areacode', 'flowtypedesc', 'round', 'rank', 'dispatch_actual', 'is_backlog', 'is_active', 'is_transit', 'is_completed', 'cycle_no']:
    if col in df_bn.columns:
        print(f"\n--- {col} ---")
        print(df_bn[col].value_counts(dropna=False).to_string())

conn.close()
