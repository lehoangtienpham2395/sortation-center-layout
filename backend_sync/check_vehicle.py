import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='enriched' AND table_name='dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]

print("Relevant columns:", [c for c in cols if any(k in c for k in ['trip', 'code', 'plate', 'vehicle', 'dispatch'])])

cur.execute("SELECT DISTINCT trip_code, dispatch_code FROM enriched.dispatch_enriched LIMIT 10;")
print("Sample trip_code / dispatch_code values:")
for r in cur.fetchall():
    print(r)

conn.close()
