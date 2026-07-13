import sqlite3, sys
import pandas as pd

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
        inbound_scanDate    as "Thời gian Inbound",
        Pickup_time         as "Thời gian lấy hàng",
        dispatchNetworkTime as "Thời gian điều phối",
        outbound_scanDate   as "Thời gian Outbound",
        weight              as "Khối lượng (kg)",
        Tuyến               as "Tuyến",
        Rank                as "Rank",
        time_ref            as "Ngày tham chiếu",
        last_updated        as "Cập nhật lần cuối"
    FROM shipments
    WHERE inbound_scanDate IS NOT NULL 
      AND inbound_scanDate != ''
    ORDER BY inbound_scanDate DESC
""", conn)

conn.close()

print(f"✅ Tổng đơn có log Inbound: {len(df):,}")
print(f"\nBreakdown theo Trạng thái:")
print(df.groupby('Trạng thái').size().reset_index(name='count').to_string(index=False))

# Save CSV
out_path = "data/export_inbound_orders.csv"
df.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f"\n💾 Đã lưu: {out_path}")
