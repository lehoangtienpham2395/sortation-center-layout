import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')
cur = conn.cursor()

# We want to find any post office and operating date where average weight is < 2.0 kg
# and count is significant (> 50).
cur.execute("""
    SELECT pickNetworkName, 
           SUBSTR(inbound_scanDate, 1, 10) as op_date,
           COUNT(*),
           SUM(weight)
    FROM shipments
    WHERE inbound_scanDate IS NOT NULL AND inbound_scanDate != ''
    GROUP BY pickNetworkName, op_date
    HAVING COUNT(*) > 50 AND SUM(weight) / COUNT(*) < 2.0
""")
rows = cur.fetchall()
conn.close()

print(f"Found {len(rows)} groups with Avg weight < 2.0 kg:")
for row in sorted(rows, key=lambda x: x[2], reverse=True):
    pkn, date, count, weight_sum = row
    avg = weight_sum / count if count > 0 else 0
    print(f"Bưu cục: {pkn} | Ngày: {date} | Số đơn: {count} | Tổng cân: {weight_sum:.2f} kg | TB: {avg:.2f} kg")
