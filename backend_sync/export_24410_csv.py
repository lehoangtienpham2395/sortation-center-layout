import psycopg2
import csv
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query all orders for Jul 31, 2026 Forecast
cur.execute('''
    SELECT 
        tracking,
        created_time
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::text, operation_date_created::text) LIKE '2026-07-31%%'
       OR operation_date_created::text LIKE '2026-07-31%%'
    ORDER BY created_time DESC;
''')

rows = cur.fetchall()

artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
csv_filepath = os.path.join(artifact_dir, "danh_sach_24410_don_forecast_31072026.csv")

with open(csv_filepath, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['mã_đơn', 'created_time'])
    for tracking, created_time in rows:
        writer.writerow([tracking, created_time])

conn.close()

print(f"Exported {len(rows):,} orders to {csv_filepath}")
