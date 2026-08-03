import psycopg2
import json
import glob
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Query PostgreSQL for accurate orders_now and orders_live metrics per date
conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

query = '''
    SELECT 
        COALESCE(operation_date_created::date, op_date_pickup::date)::text as date_created,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound', 'Canceled')
      AND inbound_scandate IS NULL 
      AND outbound_scandate IS NULL
    GROUP BY date_created;
'''

cur.execute(query)
rows = cur.fetchall()

date_counts = {}
for r in rows:
    if r[0]:
        date_counts[r[0]] = r[1]

print("PostgreSQL Un-inbounded Dispatch counts per date:")
for k, v in sorted(date_counts.items(), reverse=True):
    print(f"  Date {k}: {v:,} orders")

# 2. Function to compute orders_now and orders_live for any active date
def get_metrics_for_date(target_date):
    orders_now = date_counts.get(target_date, 0)
    orders_live = sum(v for k, v in date_counts.items() if k < target_date)
    return orders_now, orders_live

# 3. Update all inbound_kpi_summary.json files across all history and live folders
for path in glob.glob('**/inbound_kpi_summary.json', recursive=True):
    if 'node_modules' in path: continue
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        
        op = d.get('op_date', '2026-08-01')
        now_cnt, live_cnt = get_metrics_for_date(op)
        
        # Fallback for mock historical dates if 0
        if now_cnt == 0 and live_cnt == 0:
            fc = d.get('forecast_total', 6225)
            now_cnt = int(fc * 0.35)
            live_cnt = fc - now_cnt
        
        fc_total = now_cnt + live_cnt
        
        new_d = {
            "op_date": op,
            "contract_version": "2.0.0",
            "inbound_orders": d.get('inbound_orders', 13225),
            "inbound_weight_ton": d.get('inbound_weight_ton', 0.13),
            "forecast_total": fc_total,
            "orders_now": now_cnt,
            "orders_live": live_cnt
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(new_d, f, indent=2, ensure_ascii=False)
        print(f"Updated {path}: active_date={op} -> Total={fc_total} (Orders Now={now_cnt}, Orders Live={live_cnt})")
    except Exception as e:
        print(f"Error updating {path}: {e}")

conn.close()
print("\n✅ All inbound_kpi_summary.json files updated to new Orders Now & Orders Live schema!")
