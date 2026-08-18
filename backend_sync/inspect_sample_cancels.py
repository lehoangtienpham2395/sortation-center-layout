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

conn = get_pg_conn()
wbs_str = "('" + "','".join(sample_wbs) + "')"

df_samples = pd.read_sql(f"""
    SELECT *
    FROM enriched.dispatch_enriched
    WHERE tracking IN {wbs_str};
""", conn)

print("Found samples in enriched.dispatch_enriched:", len(df_samples))
if len(df_samples) > 0:
    for _, r in df_samples.iterrows():
        print(f"Tracking: {r['tracking']} | status_sys: {r.get('status_sys')} | next_station: {r.get('next_station')} | op_date: {r.get('operation_date_created')}")

# Also check all tables in DB to see where "Trạng thái đơn hàng" or raw payload is stored
df_tables = pd.read_sql("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema');
""", conn)
print("\nAll tables in database:")
print(df_tables.to_string())

conn.close()
