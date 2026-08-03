import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Check created_time / op_date_pickup distribution for 2026-08-01
cur.execute('''
    SELECT 
        EXTRACT(HOUR FROM created_time::timestamp) AS hr,
        COUNT(*) AS total_created
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
    GROUP BY hr
    ORDER BY hr;
''')

print("Hourly distribution of created_time in PostgreSQL for 2026-08-01:")
for hr, count in cur.fetchall():
    print(f"  Hour {int(hr) if hr is not None else 'NULL'}: {count:,} orders")

# Check latest created_time in DB
cur.execute('''
    SELECT MAX(created_time), MAX(inbound_scandate), MAX(op_date_pickup)
    FROM enriched.dispatch_enriched;
''')
print("\nMax timestamps in DB:")
print("  Max created_time:", cur.fetchone())

conn.close()
