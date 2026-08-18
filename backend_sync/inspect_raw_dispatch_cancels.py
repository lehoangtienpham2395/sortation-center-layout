import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

sample_wbs = [
    '530755010201', '530232750201', '530594540201', '530159600201',
    '530474540201', '530297540201', '530297340201'
]
wbs_str = "('" + "','".join(sample_wbs) + "')"

conn = get_pg_conn()
df = pd.read_sql(f"SELECT * FROM raw.raw_dispatch WHERE tracking IN {wbs_str}", conn)
print("Found in raw_dispatch:", len(df))
for _, r in df.iterrows():
    p = r['raw_payload']
    if isinstance(p, str):
        p = json.loads(p)
    print(r['tracking'], "->", {k: p.get(k) for k in ['orderStatusName', 'orderStatus', 'cancelReason', 'cancelTime', 'waybillNo', 'orderStatusCode'] if isinstance(p, dict) and k in p})

conn.close()
