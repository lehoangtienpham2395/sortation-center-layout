import sqlite3, sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

print("=== INBOUND 13/07 từ DB (06:00 → 14/07 06:00) ===")
df = pd.read_sql_query("""
    SELECT COUNT(*) as so_don, ROUND(SUM(weight),1) as tong_kg
    FROM shipments
    WHERE inbound_scanDate >= '2026-07-13 06:00:00'
      AND inbound_scanDate <  '2026-07-14 06:00:00'
""", conn)
print(df.to_string(index=False))

print("\n=== INBOUND 13/07 theo giờ ===")
df2 = pd.read_sql_query("""
    SELECT strftime('%H:00', inbound_scanDate) as gio, COUNT(*) as count
    FROM shipments
    WHERE inbound_scanDate >= '2026-07-13 06:00:00'
      AND inbound_scanDate <  '2026-07-14 06:00:00'
    GROUP BY strftime('%H', inbound_scanDate)
    ORDER BY gio
""", conn)
print(df2.to_string(index=False))
print(f"TỔNG DB 13/07: {df2['count'].sum():,}")

print("\n=== INBOUND HÔM NAY 14/07 (từ 06:00) ===")
df3 = pd.read_sql_query("""
    SELECT COUNT(*) as so_don, ROUND(SUM(weight),1) as tong_kg
    FROM shipments
    WHERE inbound_scanDate >= '2026-07-14 06:00:00'
""", conn)
print(df3.to_string(index=False))

print("\n=== inbound.json 13/07 (JSON đang deploy) ===")
import json
data = json.load(open('data/inbound.json', encoding='utf-8'))
cols = list(data[0].keys())
inb_col = cols[4]
total_json = sum(r.get('Volume',0) for r in data
                 if str(r.get(inb_col,'')).startswith('2026-07-13'))
print(f"Volume trong inbound.json ngày 13/07: {total_json:,}")

conn.close()
