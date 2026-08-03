import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]
conn.close()

print("Columns in enriched.dispatch_enriched:")
print(cols)
