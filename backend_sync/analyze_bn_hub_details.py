import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Load Backlog billcodes
df_bl = pd.read_sql("""
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
    UNION
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
""", conn)
backlog_set = set(str(x).strip() for x in df_bl['billcode'] if str(x).strip())
print(f"Total Backlog billcodes: {len(backlog_set):,}")

# Load all BN HUB un-outbounded orders from database
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
        outbound_scandate,
        is_rebound
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days')
      AND (
          next_station = 'BN HUB'
          OR next_station LIKE 'HN %'
          OR next_station LIKE 'HD %'
          OR next_station LIKE 'HY %'
          OR next_station LIKE 'HP %'
          OR next_station LIKE 'QN %'
          OR next_station LIKE 'BN %'
          OR (dispatch_code IS NOT NULL AND (
              dispatch_code LIKE 'HN%' OR dispatch_code LIKE 'BN%' OR dispatch_code LIKE 'HD%' OR
              dispatch_code LIKE 'HY%' OR dispatch_code LIKE 'HP%' OR dispatch_code LIKE 'TB%' OR
              dispatch_code LIKE 'QN%' OR dispatch_code LIKE 'PT%' OR dispatch_code LIKE 'TH%' OR
              dispatch_code LIKE 'NA%' OR dispatch_code LIKE 'HT%' OR dispatch_code LIKE 'VP%' OR
              dispatch_code LIKE 'BG%' OR dispatch_code LIKE 'BK%' OR dispatch_code LIKE 'CB%' OR
              dispatch_code LIKE 'LS%' OR dispatch_code LIKE 'LC%' OR dispatch_code LIKE 'TQ%' OR
              dispatch_code LIKE 'YB%' OR dispatch_code LIKE 'SL%' OR dispatch_code LIKE 'DB%' OR
              dispatch_code LIKE 'HG%' OR dispatch_code LIKE 'ND%' OR dispatch_code LIKE 'NB%' OR
              dispatch_code LIKE 'HA%'
          ) AND dispatch_code NOT LIKE 'TNI%' AND dispatch_code NOT LIKE 'TNG%')
      )
      AND (pickup_station IS NULL OR pickup_station NOT LIKE 'BN HUB%');
""", conn)

print(f"Total BN HUB records in DB: {len(df_bn):,}")

# Check breakdown of BN HUB orders:
# 1. Created today (2026-08-17)
# 2. Older dates (<= 2026-08-16):
#    a. Inbounded at HUB, but not in backlog source
#    b. Flag pickup = 0 & pickup_time is null (chưa từng lấy hàng)
#    c. In backlog source
#    d. In transit / Pickup done

df_bn['op_date'] = df_bn['operation_date_created'].astype(str).str[:10]
df_bn['wt_kg'] = df_bn['orders_weight'].astype(float)
df_bn['wt_ton'] = df_bn['wt_kg'] / 1000.0
df_bn['in_backlog'] = df_bn['tracking'].apply(lambda x: str(x).strip() in backlog_set)

today = '2026-08-17'

# Categories:
def categorize_bn(row):
    d = row['op_date']
    has_pk = bool(row['flag_pickup'] or row['pickup_time'])
    has_in = bool(row['flag_inbound'] or row['inbound_scandate'])
    in_bl = row['in_backlog']
    
    if d == today:
        return '1. Đơn mới tạo hôm nay (17/08)'
    
    # Older dates (< today):
    if has_in and not in_bl:
        return '2. Đã Inbound ngày cũ nhưng không có trong Backlog (Miss Outbound)'
    if not has_pk:
        return '3. Ngày cũ chưa từng lấy hàng (flag_pickup=0)'
    if in_bl:
        return '4. Ngày cũ ĐANG CÓ trong Backlog (Tồn kho thực)'
    return '5. Ngày cũ Đang vận chuyển (Pickup Done / In Transit)'

df_bn['category'] = df_bn.apply(categorize_bn, axis=1)

summary = df_bn.groupby('category').agg(
    orders=('tracking', 'count'),
    weight_ton=('wt_ton', 'sum')
).reset_index()

print("\n=== CHI TIẾT PHÂN LOẠI TOÀN BỘ ĐƠN BN HUB ===")
for _, r in summary.iterrows():
    print(f"{r['category']}: {r['orders']:,} don | {r['weight_ton']:,.3f} Tan")

conn.close()
