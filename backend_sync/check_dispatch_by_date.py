import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

conn = sqlite3.connect('backend_sync/db/state.db')

df = pd.read_sql_query("""
    SELECT 
        DATE(dispatchNetworkTime) as ngay_dispatch,
        COUNT(*) as total,
        SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active,
        SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END) as inactive
    FROM shipments
    WHERE data_source = 'Dispatch'
      AND status_order = 'Đang trên đường'
    GROUP BY DATE(dispatchNetworkTime)
    ORDER BY ngay_dispatch DESC
""", conn)

print('=== Dispatch Đang trên đường theo ngày ===')
print(df.to_string(index=False))
print(f'\nTổng ACTIVE còn đang đếm vào inventory: {df["active"].sum():,}')
print(f'Tổng INACTIVE đã loại: {df["inactive"].sum():,}')
conn.close()
