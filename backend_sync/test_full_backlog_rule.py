import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

df_bl = pd.read_sql("""
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
    UNION
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
""", conn)
backlog_set = set(str(x).strip() for x in df_bl['billcode'] if str(x).strip())
print(f"Total Backlog billcodes in source: {len(backlog_set):,}")

df_all = pd.read_sql("""
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
        outbound_scandate,
        is_rebound
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

today = '2026-08-17'
df_all['op_date'] = df_all['operation_date_created'].astype(str).str[:10]
df_all['is_canceled'] = df_all['status_sys'].astype(str).str.lower().apply(
    lambda s: any(kw in s for kw in ['hủy', 'cancel', 'da huy'])
)

def check_bn_hub(row):
    pk = str(row['pickup_station'] or '').strip().upper()
    next_st = str(row['next_station'] or '').strip().upper()
    sc = str(row['dispatch_code'] or '').strip().upper()
    return pk != 'BN HUB' and ('BN HUB' in next_st or next_st.startswith(('BN', 'HN', 'HD', 'HY', 'HP', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA')) or (sc and any(sc.startswith(pfx) for pfx in ('HN', 'BN', 'HD', 'HY', 'HP', 'TB', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA')) and not sc.startswith(('TNI', 'TNG'))))

df_all['is_bn'] = df_all.apply(check_bn_hub, axis=1)

# Apply Rule:
# If op_date < today AND tracking not in backlog_set -> Exclude
def keep_order(row):
    if row['is_canceled']:
        return False
    if row['op_date'] < today and str(row['tracking']).strip() not in backlog_set:
        return False
    return True

df_all['is_kept'] = df_all.apply(keep_order, axis=1)

kept_rows = []
for _, r in df_all.iterrows():
    if r['is_kept']:
        kept_rows.append(r)

df_kept = pd.DataFrame(kept_rows)
df_bn_kept = df_kept[df_kept['is_bn'] == True]

print("\n=== KẾT QUẢ KHI ÁP DỤNG QUY TẮC BACKLOG CHO TOÀN BỘ ĐƠN NGÀY CŨ ===")
print(f"Tổng đơn toàn HUB giữ lại: {len(df_kept):,} don | {df_kept['orders_weight'].sum()/1000.0:,.3f} Tan")
print(f"Riêng BN HUB giữ lại: {len(df_bn_kept):,} don | {df_bn_kept['orders_weight'].sum()/1000.0:,.3f} Tan")

# Breakdown of BN HUB
summary_bn = df_bn_kept.groupby('op_date').agg(
    orders=('tracking', 'count'),
    weight_ton=('orders_weight', lambda x: sum(x)/1000.0)
).reset_index()
print("\n=== PHÂN BỔ BN HUB CÒN LẠI ===")
print(summary_bn.to_string())

conn.close()
