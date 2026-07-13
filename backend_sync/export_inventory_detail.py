import sqlite3, pandas as pd, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

df = pd.read_sql_query("""
    SELECT 
        waybillNo           as "Mã vận đơn",
        data_source         as "Nguồn",
        status_order        as "Trạng thái",
        next_station        as "Điểm đến",
        pickNetworkName     as "Bưu cục lấy hàng",
        dispatch_plan       as "Tuyến phân loại",
        inbound_network     as "Điểm Inbound",
        inbound_scanDate    as "TG Inbound",
        Pickup_time         as "TG Lấy hàng",
        dispatchNetworkTime as "TG Điều phối",
        outbound_scanDate   as "TG Outbound",
        weight              as "KL (kg)",
        Tuyến, Rank, time_ref as "Ngày tham chiếu"
    FROM shipments
    WHERE is_active = 1
      AND status_order != 'Đã rời HUB'
    ORDER BY status_order, next_station
""", conn)

conn.close()
print(f"Total: {len(df):,}")
print(df.groupby('Trạng thái').size().reset_index(name='count').to_string(index=False))

df.to_csv('data/export_inventory_detail.csv', index=False, encoding='utf-8-sig')
print("Done")
