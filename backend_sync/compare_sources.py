import sqlite3, sys, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

print("=" * 60)
print("SO SÁNH 2 NGUỒN DỮ LIỆU")
print("=" * 60)

# 1. Forecast total (nguồn JFS Forecast API) - active
df_fc = pd.read_sql_query("""
    SELECT status_order, COUNT(*) as count
    FROM shipments
    WHERE is_active = 1 AND data_source = 'Forecast'
    GROUP BY status_order ORDER BY count DESC
""", conn)
fc_total = df_fc['count'].sum()
print(f"\n[1] FORECAST API (Inbound Dashboard hiển thị):")
print(df_fc.to_string(index=False))
print(f"    → TỔNG: {fc_total:,}")

# 2. Inventory total (Layout Master đọc từ DB)
df_inv = pd.read_sql_query("""
    SELECT data_source, status_order, COUNT(*) as count
    FROM shipments
    WHERE is_active = 1 AND status_order != 'Đã rời HUB'
    GROUP BY data_source, status_order ORDER BY count DESC
""", conn)
inv_total = df_inv['count'].sum()
print(f"\n[2] INVENTORY (Layout Master - tất cả nguồn active):")
print(df_inv.to_string(index=False))
print(f"    → TỔNG: {inv_total:,}")

# 3. Chênh lệch
print(f"\n{'=' * 60}")
print(f"CHÊNH LỆCH: {inv_total:,} - {fc_total:,} = {inv_total - fc_total:,} đơn")
print(f"\n→ {inv_total - fc_total:,} đơn này đến từ các nguồn NGOÀI Forecast:")
df_extra = pd.read_sql_query("""
    SELECT data_source, COUNT(*) as count
    FROM shipments
    WHERE is_active = 1 AND data_source != 'Forecast' AND status_order != 'Đã rời HUB'
    GROUP BY data_source ORDER BY count DESC
""", conn)
print(df_extra.to_string(index=False))

conn.close()
