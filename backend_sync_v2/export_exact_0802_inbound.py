import psycopg2
import pandas as pd
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Regenerating data/inbound.json & micro-JSONs from PostgreSQL for 2026-08-02 & 2026-08-03...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

# 1. Query exact reconciled dispatch_enriched records
query = '''
    SELECT 
        tracking as waybill_number,
        status_sys as status,
        COALESCE(operation_date_inbound, inbound_scandate, op_date_pickup, operation_date_created) as op_date_inbound,
        COALESCE(op_date_pickup, operation_date_created) as op_date_pickup,
        operation_date_created as op_date_created,
        COALESCE(op_date_pickup, operation_date_created) as op_date_forecast,
        inbound_scandate as arrival_time,
        CASE 
            WHEN UPPER(pickup_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'BN HUB%' THEN 'BN HUB'
            ELSE pickup_station
        END as pickup_station,
        next_station,
        orders_num as volume,
        orders_weight / 1000.0 as weight_ton,
        trip_code,
        rank
    FROM enriched.dispatch_enriched
    WHERE is_active = 1;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print(f"Loaded {len(df)} total rows from PostgreSQL.")

# Format as JSON records
records = []
for idx, r in df.iterrows():
    records.append({
        'waybill_number': str(r['waybill_number']),
        'status': str(r['status']),
        'op_date_inbound': str(r['op_date_inbound'])[:10] if pd.notnull(r['op_date_inbound']) else '',
        'op_date_pickup': str(r['op_date_pickup'])[:10] if pd.notnull(r['op_date_pickup']) else '',
        'op_date_created': str(r['op_date_created'])[:10] if pd.notnull(r['op_date_created']) else '',
        'op_date_forecast': str(r['op_date_forecast'])[:10] if pd.notnull(r['op_date_forecast']) else '',
        'op_date': str(r['op_date_inbound'])[:10] if pd.notnull(r['op_date_inbound']) else '',
        'Arrival Time': str(r['arrival_time']) if pd.notnull(r['arrival_time']) else '',
        'pickup_station': str(r['pickup_station']),
        'Volume': int(r['volume']) if pd.notnull(r['volume']) else 1,
        'weight_ton': float(r['weight_ton']) if pd.notnull(r['weight_ton']) else 0.0,
        'trip_code': str(r['trip_code']) if pd.notnull(r['trip_code']) else '',
        'rank': str(r['rank']) if pd.notnull(r['rank']) else 'Shuttle'
    })

# Save to data/inbound.json
with open('data/inbound.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print("✅ data/inbound.json successfully regenerated from PostgreSQL!")
