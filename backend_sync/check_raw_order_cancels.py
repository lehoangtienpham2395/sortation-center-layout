import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

sample_wbs = [
    '530755010201',
    '530232750201',
    '530594540201',
    '530159600201',
    '530474540201',
    '530297540201',
    '530297340201'
]
wbs_str = "('" + "','".join(sample_wbs) + "')"

conn = get_pg_conn()

for tbl in ['kpi_hub.raw_order', 'kpi_hub.raw_order_live', 'raw.raw_dispatch']:
    try:
        df = pd.read_sql(f"SELECT * FROM {tbl} WHERE billcode IN {wbs_str} OR tracking IN {wbs_str} LIMIT 5", conn)
        print(f"\n--- {tbl} (found {len(df)}) ---")
        if len(df) > 0:
            print(df.to_string())
    except Exception as e:
        print(f"Error checking {tbl}: {e}")

conn.close()
