import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)

# Query breakdown for Orders Now (Created today) and Orders Live (Created previous dates & still un-inbounded/un-outbounded)
query = '''
    SELECT 
        COALESCE(operation_date_created::date, op_date_pickup::date) as date_created,
        status_sys,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound', 'Canceled')
      AND inbound_scandate IS NULL 
      AND outbound_scandate IS NULL
    GROUP BY date_created, status_sys
    ORDER BY date_created DESC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("Un-inbounded & Un-outbounded Dispatch Orders breakdown by Creation Date:")
print(df)

today_date = '2026-08-01' # or 2026-08-03
orders_now = df[df['date_created'] == pd.to_datetime(today_date).date()]['cnt'].sum()
orders_live = df[df['date_created'] < pd.to_datetime(today_date).date()]['cnt'].sum()
total_fc = orders_now + orders_live

print(f"\nFor Active Date = {today_date}:")
print(f"-> ORDERS NOW (Created Today {today_date}): {orders_now:,}")
print(f"-> ORDERS LIVE (Created Previous Dates < {today_date}): {orders_live:,}")
print(f"-> TOTAL FORECAST: {total_fc:,}")
