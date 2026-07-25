import sqlite3, sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

# 1. Tổng active hiện tại
import pandas as pd
df_total = pd.read_sql_query("SELECT COUNT(*) as c FROM shipments WHERE is_active = 1", conn)
print(f"Tổng active trong DB: {df_total['c'].values[0]:,}")

# 2. Breakdown
df = pd.read_sql_query("""
    SELECT status_order, data_source, COUNT(*) as count
    FROM shipments WHERE is_active = 1
    GROUP BY status_order, data_source
    ORDER BY count DESC
""", conn)
print("\nBreakdown:")
print(df.to_string(index=False))
print(f"\nGrand total from breakdown: {df['count'].sum():,}")

# 3. Kiểm tra inventory.json đang có bao nhiêu
inv_path = 'data/inventory.json'
if os.path.exists(inv_path):
    with open(inv_path, encoding='utf-8') as f:
        inv = json.load(f)
    total_inv = sum(row.get('count', 0) for row in inv)
    print(f"\ninventory.json tổng count: {total_inv:,} | rows: {len(inv)}")

conn.close()
