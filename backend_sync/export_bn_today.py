import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

today = '2026-08-18'

# Query all BN HUB orders for today or active in forecast
df_bn = pd.read_sql(f"""
    SELECT 
        tracking as "Mã vận đơn",
        status_sys as "Trạng thái hệ thống",
        operation_date_created as "Ngày tạo đơn",
        created_time as "Thời gian tạo đơn",
        pickup_station as "Bưu cục gửi (Pickup Station)",
        next_station as "Điểm tiếp theo (Next Station)",
        dispatch_code as "Mã điều phối (Dispatch Code)",
        orders_weight as "Khối lượng tính cước (g)",
        ROUND(orders_weight / 1000.0, 3) as "Khối lượng (Kg)",
        flag_pickup as "Đã lấy hàng (Pickup)",
        pickup_time as "Thời gian lấy hàng",
        flag_inbound as "Đã nhập kho (Inbound)",
        inbound_scandate as "Thời gian Inbound",
        outbound_scandate as "Thời gian Outbound",
        goods_name as "Tên hàng hóa",
        send_name as "Người gửi",
        receiver_name as "Người nhận",
        receiver_province as "Tỉnh nhận",
        receiver_city as "Huyện/TP nhận",
        receiver_address as "Địa chỉ nhận"
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
      AND operation_date_created::date = '{today}'
    ORDER BY created_time DESC;
""", conn)

print(f"Total BN HUB orders for today ({today}): {len(df_bn):,}")
total_wt_kg = df_bn['Khối lượng (Kg)'].sum()
total_wt_ton = total_wt_kg / 1000.0
print(f"Total Weight: {total_wt_kg:,.2f} Kg ({total_wt_ton:,.3f} Ton)")

# Also query if next_station = 'BN HUB' strictly
df_strict = df_bn[df_bn['Điểm tiếp theo (Next Station)'] == 'BN HUB']
print(f"Strict next_station == 'BN HUB': {len(df_strict):,}")

# Export to Excel & CSV
excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f"DS_Don_BN_HUB_HomNay_{today}_{len(df_bn)}.xlsx")
csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f"DS_Don_BN_HUB_HomNay_{today}_{len(df_bn)}.csv")

df_bn.to_excel(excel_path, index=False, engine='openpyxl')
df_bn.to_csv(csv_path, index=False, encoding='utf-8-sig')

print(f"✅ Exported Excel: {excel_path}")
print(f"✅ Exported CSV: {csv_path}")

# Breakdown by status
print("\n--- Status Breakdown ---")
print(df_bn['Trạng thái hệ thống'].value_counts())

conn.close()
