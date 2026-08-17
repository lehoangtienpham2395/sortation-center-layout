import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

df_bn = pd.read_sql("""
    SELECT 
        tracking,
        status_sys,
        operation_date_created,
        created_time,
        pickup_station,
        next_station,
        dispatch_code,
        orders_weight,
        flag_pickup,
        pickup_time,
        flag_inbound,
        inbound_scandate,
        outbound_scandate
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND (next_station = 'BN HUB' OR next_station LIKE 'HN %' OR next_station LIKE 'BN %')
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

df_bn['op_date'] = df_bn['operation_date_created'].astype(str).str[:10]
today = '2026-08-17'

print(f"Total BN HUB records: {len(df_bn)}")

# Breakdown of older orders (op_date < today)
df_older = df_bn[df_bn['op_date'] < today]
print(f"\nTotal older BN HUB records (before 17/08): {len(df_older)}")

# Check flag_pickup in older orders
print("\nOlder BN HUB orders by flag_pickup:")
print(df_older['flag_pickup'].value_counts())

# Check pickup_time is null in older orders
print("\nOlder BN HUB orders pickup_time is NULL:")
print(df_older['pickup_time'].isnull().value_counts())

# Check status_sys in older orders
print("\nOlder BN HUB orders status_sys:")
print(df_older['status_sys'].value_counts())

# Look at older orders where flag_pickup = 0 AND pickup_time IS NULL
df_no_pickup = df_older[(df_older['flag_pickup'] == 0) | (df_older['pickup_time'].isnull())]
print(f"\nOlder BN HUB orders with NO PICKUP (chưa từng lấy hàng): {len(df_no_pickup)} don | {df_no_pickup['orders_weight'].sum()/1000.0:.3f} Tan")

# Look at today orders where flag_pickup = 0
df_today = df_bn[df_bn['op_date'] == today]
print(f"\nToday BN HUB orders: {len(df_today)}")
print("Today BN HUB orders by status_sys:")
print(df_today['status_sys'].value_counts())
print("Today BN HUB orders by flag_pickup:")
print(df_today['flag_pickup'].value_counts())

conn.close()
