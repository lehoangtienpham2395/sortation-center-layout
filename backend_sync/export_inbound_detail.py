import sqlite3, sys
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding='utf-8')

tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
now = datetime.now(tz_vn)

# Ngày vận hành hôm nay: từ 06:00 hôm nay đến 06:00 ngày mai
# Nếu trước 06:00 thì lấy từ 06:00 hôm qua
if now.hour < 6:
    op_start = now.replace(hour=6, minute=0, second=0, microsecond=0) - timedelta(days=1)
else:
    op_start = now.replace(hour=6, minute=0, second=0, microsecond=0)

op_start_str = op_start.strftime('%Y-%m-%d %H:%M:%S')
op_end_str   = (op_start + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

print(f"Ngày vận hành: {op_start_str} → {op_end_str}")

conn = sqlite3.connect('backend_sync/db/state.db')

# Lấy tất cả đơn có Inbound scan trong ngày vận hành hôm nay
df = pd.read_sql_query(f"""
    SELECT 
        waybillNo           as "Mã vận đơn",
        pickNetworkName     as "Bưu cục lấy hàng",
        next_station        as "Điểm đến",
        dispatch_plan       as "Tuyến phân loại",
        inbound_network     as "Điểm Inbound",
        inbound_scanDate    as "Thời gian Inbound",
        Pickup_time         as "Thời gian lấy hàng",
        dispatchNetworkTime as "Thời gian điều phối",
        outbound_scanDate   as "Thời gian Outbound",
        status_order        as "Trạng thái",
        weight              as "Khối lượng (kg)",
        Tuyến               as "Tuyến",
        Rank                as "Rank",
        data_source         as "Nguồn"
    FROM shipments
    WHERE inbound_scanDate IS NOT NULL 
      AND inbound_scanDate != ''
      AND inbound_scanDate >= '{op_start_str}'
      AND inbound_scanDate < '{op_end_str}'
    ORDER BY inbound_scanDate DESC
""", conn)

conn.close()

print(f"✅ Tổng đơn Inbound hôm nay ({op_start.strftime('%d/%m/%Y')}): {len(df):,}")

out_path = "data/export_inbound_detail.csv"
df.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f"💾 Lưu: {out_path}")
