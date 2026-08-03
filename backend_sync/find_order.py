import psycopg2
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

tracking_no = '530843900108'

# Get column names
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='enriched' AND table_name='dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]

cur.execute("SELECT * FROM enriched.dispatch_enriched WHERE tracking = %s;", (tracking_no,))
rows = cur.fetchall()

if not rows:
    print(f"❌ Không tìm thấy tracking '{tracking_no}' trong bảng enriched.dispatch_enriched!")
else:
    print(f"=== CHI TIẾT ĐƠN HÀNG {tracking_no} TRONG POSTGRESQL ===")
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if v is not None and str(v) != 'nan':
                print(f"{k:<30}: {v}")

conn.close()
