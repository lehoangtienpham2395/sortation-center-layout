import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Check for cancel keywords in raw_dispatch
df_cancel_raw = pd.read_sql("""
    SELECT count(*) as total_canceled_in_raw
    FROM raw.raw_dispatch
    WHERE CAST(raw_payload AS text) ILIKE '%hủy%' 
       OR CAST(raw_payload AS text) ILIKE '%cancel%' 
       OR CAST(raw_payload AS text) ILIKE '%đã hủy%';
""", conn)
print("\nTotal cancelled orders found in raw_dispatch:", df_cancel_raw.to_string())

# Search what fields exist in raw_payload containing 'status' or 'cancel'
sample_rows = pd.read_sql("""
    SELECT tracking, raw_payload
    FROM raw.raw_dispatch
    WHERE CAST(raw_payload AS text) ILIKE '%hủy%' OR CAST(raw_payload AS text) ILIKE '%cancel%'
    LIMIT 5;
""", conn)

for _, r in sample_rows.iterrows():
    p = r['raw_payload'] if isinstance(r['raw_payload'], dict) else {}
    print("\nTracking:", r['tracking'])
    for k, v in p.items():
        if any(w in str(k).lower() or w in str(v).lower() for w in ['status', 'hủy', 'cancel', 'state', 'orderstatus', 'billstatus']):
            print(f"  {k}: {v}")

# Also check all unique status / cancel values across raw_dispatch
df_statuses = pd.read_sql("""
    SELECT 
        raw_payload->>'orderStatusName' as order_status_name,
        raw_payload->>'orderStatus' as order_status,
        raw_payload->>'status' as status_raw,
        raw_payload->>'billStatus' as bill_status,
        raw_payload->>'cancelFlag' as cancel_flag,
        COUNT(*) as cnt
    FROM raw.raw_dispatch
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY cnt DESC;
""", conn)
print("\nUnique Status combinations in raw_dispatch:")
print(df_statuses.to_string())

conn.close()
