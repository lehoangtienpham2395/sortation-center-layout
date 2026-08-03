import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)

# Analyze all un-inbounded/un-outbounded orders by creation date
query = '''
    SELECT 
        COALESCE(operation_date_created::date, op_date_pickup::date) as op_date,
        status_sys,
        COUNT(*) as order_count
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound', 'Canceled')
      AND inbound_scandate IS NULL 
      AND outbound_scandate IS NULL
    GROUP BY op_date, status_sys
    ORDER BY op_date DESC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print("📊 Breakdown of the 49,003 un-inbounded/un-outbounded Dispatch orders by Creation Operating Date:\n")
print(df.to_string(index=False))

print("\nSummary by Date:")
summary_by_date = df.groupby('op_date')['order_count'].sum().reset_index()
summary_by_date['cum_sum'] = summary_by_date['order_count'].cumsum()
print(summary_by_date.to_string(index=False))
