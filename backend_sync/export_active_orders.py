import sqlite3, sys, os
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

df = pd.read_sql_query("""
    SELECT 
        waybillNo       as "Mã vận đơn",
        data_source     as "Nguồn",
        status_order    as "Trạng thái",
        next_station    as "Điểm đến",
        pickNetworkName as "Bưu cục lấy hàng",
        dispatch_plan   as "Tuyến phân loại",
        Pickup_time     as "Thời gian lấy hàng",
        dispatchNetworkTime as "Thời gian điều phối",
        inbound_scanDate    as "Thời gian Inbound",
        outbound_scanDate   as "Thời gian Outbound",
        weight          as "Khối lượng (kg)",
        Tuyến           as "Tuyến",
        Rank            as "Rank",
        time_ref        as "Ngày tham chiếu",
        last_updated    as "Cập nhật lần cuối"
    FROM shipments
    WHERE is_active = 1
      AND status_order != 'Đã rời HUB'
    ORDER BY status_order, next_station, waybillNo
""", conn)

conn.close()

out_path = 'data/export_active_orders.csv'
df.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f"✅ Xuất {len(df):,} đơn ra: {out_path}")
print(f"\nBreakdown:")
print(df.groupby(['Nguồn', 'Trạng thái']).size().reset_index(name='count').to_string(index=False))
