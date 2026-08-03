import psycopg2
import pandas as pd
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Auditing BN HUB Inbound Orders for 2026-08-02...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

# 1. Query BN HUB orders in PostgreSQL for 2026-08-02
query = '''
    SELECT 
        pickup_station,
        next_station,
        trip_code,
        dispatch_code,
        COUNT(*) as order_count,
        SUM(orders_weight) as total_weight_kg
    FROM enriched.dispatch_enriched
    WHERE inbound_scandate::date = '2026-08-02'::date
      AND (UPPER(pickup_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'BN HUB%')
    GROUP BY pickup_station, next_station, trip_code, dispatch_code
    ORDER BY order_count DESC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("=== PostgreSQL BN HUB Inbound Orders Breakdown (2026-08-02) ===")
print(df.to_string(index=False))

# 2. Inspect data/inbound.json for BN HUB rows on 2026-08-02
with open('data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

rows = data if isinstance(data, list) else data.get('data', [])

bn_rows_0802 = []
for r in rows:
    st = (r.get('pickup_station') or r.get('send_network') or r.get('Bưu cục') or '').strip().upper()
    inb_dt = r.get('op_date_inbound') or r.get('Ngày vận hành_Inbound') or r.get('op_date_created') or ''
    if 'BN HUB' in st and '2026-08-02' in str(inb_dt):
        bn_rows_0802.append(r)

print(f"\nFound {len(bn_rows_0802)} rows strictly for BN HUB on 2026-08-02 in inbound.json")
