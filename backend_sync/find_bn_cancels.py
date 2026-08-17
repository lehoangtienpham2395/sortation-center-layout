import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd
import json

conn = get_pg_conn()

# Check raw_dispatch for BN HUB orders that have cancel in their payload or status
df_raw_bn = pd.read_sql("""
    SELECT 
        de.tracking,
        de.status_sys,
        de.operation_date_created,
        de.created_time,
        de.pickup_station,
        de.next_station,
        de.orders_weight,
        de.flag_pickup,
        de.pickup_time,
        rd.raw_payload
    FROM enriched.dispatch_enriched de
    LEFT JOIN raw.raw_dispatch rd ON de.tracking = rd.tracking
    WHERE de.outbound_scandate IS NULL
      AND (de.next_station = 'BN HUB' OR de.next_station LIKE 'HN %' OR de.next_station LIKE 'BN %')
      AND de.operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

print(f"Total BN HUB records in query: {len(df_raw_bn)}")

# Check payload keys and status values for these BN HUB orders
cancel_matches = []
status_names = {}
order_status_vals = {}
bill_status_vals = {}

for _, r in df_raw_bn.iterrows():
    p = r['raw_payload']
    if isinstance(p, dict):
        osn = str(p.get('orderStatusName') or '')
        os_val = str(p.get('orderStatus') or '')
        bsn = str(p.get('billStatusName') or p.get('billStatus') or '')
        cf = str(p.get('cancelFlag') or p.get('isCancel') or '')
        
        status_names[osn] = status_names.get(osn, 0) + 1
        order_status_vals[os_val] = order_status_vals.get(os_val, 0) + 1
        bill_status_vals[bsn] = bill_status_vals.get(bsn, 0) + 1
        
        # Check if any field contains cancel
        p_str = json.dumps(p, ensure_ascii=False).lower()
        if any(w in p_str for w in ['hủy', 'cancel', 'da huy']):
            cancel_matches.append((r['tracking'], osn, os_val, bsn, cf))

print("\n--- orderStatusName distribution in BN HUB raw payloads ---")
for k, v in sorted(status_names.items(), key=lambda x: x[1], reverse=True):
    print(f"  '{k}': {v} orders")

print("\n--- orderStatus (code) distribution ---")
for k, v in sorted(order_status_vals.items(), key=lambda x: x[1], reverse=True):
    print(f"  '{k}': {v} orders")

print(f"\nTotal BN HUB orders with cancel keyword in raw payload: {len(cancel_matches)}")
if cancel_matches:
    print("Sample cancel matches:", cancel_matches[:10])

conn.close()
