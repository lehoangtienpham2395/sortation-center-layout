import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')
cur = conn.cursor()

# We want to find any post office (pickNetworkName) and operating date (inbound_scanDate's operating date)
# with total count ~512 or total weight ~360.
cur.execute("""
    SELECT pickNetworkName, 
           SUBSTR(inbound_scanDate, 1, 10) as op_date,
           COUNT(*),
           SUM(weight)
    FROM shipments
    WHERE inbound_scanDate IS NOT NULL AND inbound_scanDate != ''
    GROUP BY pickNetworkName, op_date
""")
rows = cur.fetchall()
conn.close()

matches = []
for row in rows:
    pkn, date, count, weight_sum = row
    if weight_sum is None:
        weight_sum = 0.0
    # Search for count close to 512 or weight close to 360
    if (480 <= count <= 550) or (300 <= weight_sum <= 420 and count > 100):
        matches.append((pkn, date, count, weight_sum))

print(f"Found {len(matches)} potential matching bưu cục + date groups:")
for pkn, date, count, weight_sum in sorted(matches, key=lambda x: x[2], reverse=True):
    avg = weight_sum / count if count > 0 else 0
    print(f"Bưu cục: {pkn} | Ngày: {date} | Số đơn: {count} | Tổng cân: {weight_sum:.2f} kg | TB: {avg:.2f} kg")
