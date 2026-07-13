import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')
c = conn.cursor()

# 1. Tắt đơn Dispatch cũ > 2 ngày không có inbound/pickup
c.execute("""
    UPDATE shipments
    SET is_active = 0, last_updated = CURRENT_TIMESTAMP
    WHERE is_active = 1
      AND data_source = 'Dispatch'
      AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
      AND (outbound_scanDate = '' OR outbound_scanDate IS NULL)
      AND (Pickup_time = '' OR Pickup_time IS NULL)
      AND dispatchNetworkTime != '' AND dispatchNetworkTime IS NOT NULL
      AND datetime(dispatchNetworkTime) < datetime('now', '+7 hours', '-2 days')
""")
cnt_dispatch = c.rowcount
print(f"✅ Đã tắt {cnt_dispatch:,} đơn Dispatch cũ > 2 ngày")

# 2. Tắt đơn Forecast/Pickup cũ > 3 ngày không có inbound
c.execute("""
    UPDATE shipments 
    SET is_active = 0, last_updated = CURRENT_TIMESTAMP
    WHERE is_active = 1
      AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
      AND (
        (Pickup_time != '' AND Pickup_time IS NOT NULL AND datetime(Pickup_time) < datetime('now', '+7 hours', '-3 days'))
        OR
        ((Pickup_time = '' OR Pickup_time IS NULL) AND date(time_ref) < date('now', '+7 hours', '-3 days'))
      )
""")
cnt_fc = c.rowcount
print(f"✅ Đã tắt {cnt_fc:,} đơn Forecast/Pickup cũ > 3 ngày")

conn.commit()

# Kiểm tra lại tổng sau cleanup
c.execute("SELECT COUNT(*) FROM shipments WHERE is_active = 1")
total = c.fetchone()[0]
print(f"\n📊 Tổng đơn active sau cleanup: {total:,}")

# Breakdown theo status
import pandas as pd
df = pd.read_sql_query("""
    SELECT status_order, data_source, COUNT(*) as count
    FROM shipments WHERE is_active = 1
    GROUP BY status_order, data_source
    ORDER BY count DESC
""", conn)
print("\n=== Breakdown by status + source ===")
print(df.to_string(index=False))

conn.close()
