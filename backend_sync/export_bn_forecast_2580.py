import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Query all un-outbounded BN HUB forecast orders
query = """
    SELECT 
        tracking as "Mã vận đơn",
        status_sys as "Trạng thái hệ thống",
        operation_date_created::text as "Ngày vận hành",
        created_time::text as "Thời gian tạo đơn",
        pickup_station as "Bưu cục gửi (Pickup Station)",
        next_station as "Điểm tiếp theo (Next Station)",
        dispatch_code as "Mã điều phối (Dispatch Code)",
        ROUND(orders_weight::numeric, 3) as "Khối lượng tính cước (Kg)",
        CASE WHEN flag_pickup = 1 THEN 'Đã lấy' ELSE 'Chưa lấy' END as "Trạng thái lấy hàng",
        pickup_time::text as "Thời gian lấy hàng",
        CASE WHEN flag_inbound = 1 THEN 'Đã nhập' ELSE 'Chưa nhập' END as "Trạng thái Inbound",
        inbound_scandate::text as "Thời gian quét Inbound",
        outbound_scandate::text as "Thời gian quét Outbound",
        trip_code as "Mã chuyến xe",
        flowtypedesc as "Luồng vận chuyển",
        round as "Phân loại Round",
        rank as "Phân loại Rank",
        areacode as "Mã khu vực"
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
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
      AND (pickup_station IS NULL OR pickup_station NOT LIKE 'BN HUB%')
      AND (status_sys IS NULL OR (status_sys NOT ILIKE '%hủy%' AND status_sys NOT ILIKE '%cancel%'))
      AND operation_date_created::date >= ('2026-08-18'::date - INTERVAL '15 days')
    ORDER BY operation_date_created DESC, created_time DESC;
"""

df_bn = pd.read_sql(query, conn)
conn.close()

# Format all datetime / object fields to string without timezone
for col in df_bn.columns:
    if df_bn[col].dtype == 'object':
        df_bn[col] = df_bn[col].fillna('').astype(str)

total_orders = len(df_bn)
total_kg = df_bn['Khối lượng tính cước (Kg)'].astype(float).sum()
total_ton = total_kg / 1000.0

print(f"📊 Tổng số đơn BN HUB: {total_orders:,} đơn")
print(f"⚖️ Tổng khối lượng: {total_kg:,.2f} Kg ({total_ton:,.3f} Tấn)")

# Base project dir
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
excel_filename = f"DS_Don_BN_HUB_DuBao_{total_orders}.xlsx"
csv_filename = f"DS_Don_BN_HUB_DuBao_{total_orders}.csv"

excel_path = os.path.join(base_dir, excel_filename)
csv_path = os.path.join(base_dir, csv_filename)

df_bn.to_excel(excel_path, index=False, engine='openpyxl')
df_bn.to_csv(csv_path, index=False, encoding='utf-8-sig')

print(f"✅ Đã lưu Excel: {excel_path}")
print(f"✅ Đã lưu CSV: {csv_path}")

# Breakdown by Date
print("\n--- Phân bổ theo Ngày vận hành ---")
summary_date = df_bn.groupby('Ngày vận hành').agg(
    orders=('Mã vận đơn', 'count'),
    weight_kg=('Khối lượng tính cước (Kg)', lambda x: sum(x.astype(float)))
).reset_index()
summary_date['weight_ton'] = summary_date['weight_kg'] / 1000.0
summary_date = summary_date.sort_values(by='Ngày vận hành', ascending=False)
print(summary_date.to_string(index=False))

# Breakdown by Status
print("\n--- Phân bổ theo Trạng thái ---")
summary_stt = df_bn.groupby('Trạng thái hệ thống').agg(
    orders=('Mã vận đơn', 'count'),
    weight_kg=('Khối lượng tính cước (Kg)', lambda x: sum(x.astype(float)))
).reset_index()
summary_stt['weight_ton'] = summary_stt['weight_kg'] / 1000.0
print(summary_stt.to_string(index=False))
