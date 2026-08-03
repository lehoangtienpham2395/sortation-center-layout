import psycopg2
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)

# Test limiting ORDERS LIVE to last 1 day (yesterday) vs last 2 days vs all past days
query = '''
    SELECT 
        COALESCE(operation_date_created::date, op_date_pickup::date) as op_date,
        CASE 
            WHEN UPPER(rank) = 'LINEHAUL' OR UPPER(next_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'HN %' OR UPPER(next_station) LIKE 'HD %' OR UPPER(next_station) LIKE 'HY %' OR UPPER(pickup_station) LIKE 'BN HUB%' THEN 'Linehaul'
            ELSE 'Shuttle'
        END as route_type,
        COUNT(*) as cnt
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound', 'Canceled')
      AND inbound_scandate IS NULL 
      AND outbound_scandate IS NULL
    GROUP BY op_date, route_type
    ORDER BY op_date DESC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

active_date = '2026-08-03'

# 1. All past days (Current logic -> 49,003)
all_past = df[df['op_date'] <= pd.to_datetime(active_date).date()]
print(f"Option A - All Past Days (Total={all_past['cnt'].sum():,}):")
print(all_past.groupby('route_type')['cnt'].sum())

# 2. Limit ORDERS LIVE to yesterday + today (2 days window)
two_days = df[df['op_date'].isin([pd.to_datetime('2026-08-03').date(), pd.to_datetime('2026-08-02').date()])]
print(f"\nOption B - Today + Yesterday only (Total={two_days['cnt'].sum():,}):")
print(two_days.groupby('route_type')['cnt'].sum())

# 3. Limit ORDERS LIVE to 3 days (Aug 1, Aug 2, Aug 3)
three_days = df[df['op_date'].isin([pd.to_datetime('2026-08-03').date(), pd.to_datetime('2026-08-02').date(), pd.to_datetime('2026-08-01').date()])]
print(f"\nOption C - Today + 2 Days Back (Aug 1 - Aug 3) (Total={three_days['cnt'].sum():,}):")
print(three_days.groupby('route_type')['cnt'].sum())
