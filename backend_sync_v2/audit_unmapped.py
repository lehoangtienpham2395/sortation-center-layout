import psycopg2
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

valid_sc = set()
valid_st = set()
with open('backend_sync/config/valid.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if r.get('sortcode'): valid_sc.add(r['sortcode'].strip().upper())
        if r.get('Station_1'): valid_st.add(r['Station_1'].strip().upper())
        if r.get('Station_2'): valid_st.add(r['Station_2'].strip().upper())

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

cur.execute('''
    SELECT 
        COALESCE(NULLIF(TRIM(next_station), ''), 'TRỐNG') as next_st,
        COALESCE(NULLIF(TRIM(dispatch_code), ''), 'TRỐNG') as sc,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-01'::date
      AND status_sys != 'Outbound'
    GROUP BY 1, 2
    ORDER BY cnt DESC;
''')

unmapped_list = []
for next_st, sc, cnt in cur.fetchall():
    n_up = next_st.upper()
    s_up = sc.upper()
    is_north = (n_up == 'BN HUB' or n_up.startswith(('HN ', 'HD ', 'HY ')))
    if not is_north and s_up not in valid_sc and n_up not in valid_st:
        unmapped_list.append((next_st, sc, cnt))

print(f"Total unmapped (next_station, dispatch_code) pairs found: {len(unmapped_list)}")
for n_st, sc, cnt in unmapped_list[:20]:
    print(f" - NextStation: '{n_st}' | DispatchCode: '{sc}' -> {cnt} orders")
conn.close()
