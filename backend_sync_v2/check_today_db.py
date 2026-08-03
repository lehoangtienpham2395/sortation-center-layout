import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

cur.execute('''
    SELECT 
        status_sys,
        COUNT(*) as cnt,
        COALESCE(SUM(orders_weight), 0)::numeric / 1000000.0 as wt_ton
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
    GROUP BY 1
    ORDER BY cnt DESC;
''')
rows = cur.fetchall()

print('=== TODAY (2026-08-01) STATUS BREAKDOWN IN POSTGRESQL ===')
tot_cnt = 0
tot_wt = 0.0
for status, cnt, wt in rows:
    tot_cnt += cnt
    tot_wt += float(wt)
    print(f" - Status: '{status}' -> {cnt:,} orders | {float(wt):.2f} Tấn")

print(f"\nTOTAL ACTIVE ORDERS TODAY (2026-08-01): {tot_cnt:,} orders | {tot_wt:.2f} Tấn")

cur.execute('''
    SELECT COUNT(*), COALESCE(SUM(orders_weight), 0)::numeric / 1000000.0
    FROM enriched.dispatch_enriched
    WHERE inbound_scandate::date = '2026-08-01'::date;
''')
inb_cnt, inb_wt = cur.fetchone()
print(f"ACTUAL INBOUND SCANS TODAY (2026-08-01): {inb_cnt:,} orders | {float(inb_wt):.2f} Tấn")

conn.close()
