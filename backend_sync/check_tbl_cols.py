import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

for tbl in ['kpi_hub.raw_order', 'kpi_hub.raw_order_live', 'raw.raw_dispatch', 'raw.scan_logs']:
    try:
        df = pd.read_sql(f"SELECT * FROM {tbl} LIMIT 1", conn)
        print(f"\n--- Columns in {tbl} ---")
        print(list(df.columns))
    except Exception as e:
        print(f"Error {tbl}: {e}")

conn.close()
