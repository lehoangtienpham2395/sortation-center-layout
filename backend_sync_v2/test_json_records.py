import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Query counts for 2026-08-01 by operation date fields
cur.execute('''
    SELECT 
        COUNT(*) AS total_all,
        COUNT(CASE WHEN operation_date_created = '2026-08-01' THEN 1 END) AS op_cr_01,
        COUNT(CASE WHEN op_date_pickup = '2026-08-01' THEN 1 END) AS op_pk_01,
        COUNT(CASE WHEN COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01' THEN 1 END) AS op_coalesce_01
    FROM enriched.dispatch_enriched;
''')

print("Counts in PostgreSQL enriched.dispatch_enriched:")
print(cur.fetchone())

# Query orders with created_time on 2026-08-01 vs operation_date_created
cur.execute('''
    SELECT 
        COUNT(CASE WHEN created_time::date = '2026-08-01' THEN 1 END) as created_time_01,
        COUNT(CASE WHEN operation_date_created = '2026-08-01' THEN 1 END) as op_created_01
    FROM enriched.dispatch_enriched;
''')
print("Created time vs Operation Date Created:", cur.fetchone())

conn.close()
