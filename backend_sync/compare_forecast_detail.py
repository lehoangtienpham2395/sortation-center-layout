import sqlite3, sys, pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

# ──────────────────────────────────────────────────────────
# FILE 1: DB Forecast ACTIVE (đang được tính vào dashboard)
# ──────────────────────────────────────────────────────────
df_active = pd.read_sql_query("""
    SELECT 
        waybillNo               as "Mã vận đơn",
        status_order            as "Trạng thái DB",
        pickNetworkName         as "Bưu cục lấy hàng",
        next_station            as "Điểm đến",
        dispatch_plan           as "Tuyến phân loại",
        Pickup_time             as "TG Lấy hàng",
        dispatchNetworkTime     as "TG Forecast (Điều phối)",
        inbound_scanDate        as "TG Inbound",
        outbound_scanDate       as "TG Outbound",
        weight                  as "KL (kg)",
        time_ref                as "Ngày tham chiếu",
        1                       as "is_active"
    FROM shipments
    WHERE data_source = 'Forecast' AND is_active = 1
    ORDER BY dispatchNetworkTime DESC
""", conn)

# ──────────────────────────────────────────────────────────
# FILE 2: DB Forecast INACTIVE (bị cleanup, không được tính)
# ──────────────────────────────────────────────────────────
df_inactive = pd.read_sql_query("""
    SELECT 
        waybillNo               as "Mã vận đơn",
        status_order            as "Trạng thái DB",
        pickNetworkName         as "Bưu cục lấy hàng",
        next_station            as "Điểm đến",
        dispatch_plan           as "Tuyến phân loại",
        Pickup_time             as "TG Lấy hàng",
        dispatchNetworkTime     as "TG Forecast (Điều phối)",
        inbound_scanDate        as "TG Inbound",
        outbound_scanDate       as "TG Outbound",
        weight                  as "KL (kg)",
        time_ref                as "Ngày tham chiếu",
        0                       as "is_active"
    FROM shipments
    WHERE data_source = 'Forecast' AND is_active = 0
    ORDER BY dispatchNetworkTime DESC
""", conn)

conn.close()

# Save files
df_active.to_csv('data/compare_A_forecast_active_db.csv', index=False, encoding='utf-8-sig')
df_inactive.to_csv('data/compare_B_forecast_inactive_db.csv', index=False, encoding='utf-8-sig')

print(f"[FILE A] Forecast ACTIVE trong DB: {len(df_active):,} đơn")
print(f"         → Đây là nguồn dashboard đang dùng")
print(f"\n[FILE B] Forecast INACTIVE (đã bị cleanup): {len(df_inactive):,} đơn")
print(f"         → Những đơn này bị loại khỏi dashboard")

print(f"\nTổng Forecast trong DB (A + B): {len(df_active)+len(df_inactive):,}")
print(f"Dashboard hiển thị: 19.664")
print(f"Chênh lệch (A vs dashboard): 19.664 - {len(df_active):,} = {19664 - len(df_active):,} đơn")
print(f"\n→ INACTIVE đóng góp bao nhiêu vào chênh lệch:")
print(df_inactive.groupby('Trạng thái DB').size().reset_index(name='count').to_string(index=False))
