import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Check Backlog source for all BN HUB orders
df_bn_bl = pd.read_sql("""
    SELECT 
        de.tracking,
        de.operation_date_created,
        de.orders_weight,
        de.status_sys,
        de.pickup_station,
        de.next_station,
        bl.billcode as in_backlog
    FROM enriched.dispatch_enriched de
    LEFT JOIN (
        SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
        UNION
        SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
    ) bl ON de.tracking = bl.billcode
    WHERE de.outbound_scandate IS NULL
      AND (de.next_station = 'BN HUB' OR de.next_station LIKE 'HN %' OR de.next_station LIKE 'BN %')
      AND de.operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

print(f"Total BN HUB records: {len(df_bn_bl):,}")

# Breakdown by today vs older & in_backlog
df_bn_bl['is_today'] = df_bn_bl['operation_date_created'].astype(str).str[:10] == '2026-08-17'
df_bn_bl['has_backlog'] = df_bn_bl['in_backlog'].notnull()

summary = df_bn_bl.groupby(['is_today', 'has_backlog']).agg(
    orders=('tracking', 'count'),
    weight_kg=('orders_weight', 'sum')
).reset_index()
summary['weight_ton'] = summary['weight_kg'] / 1000.0

print("\n=== BN HUB BREAKDOWN BY DATE & BACKLOG EXISTENCE ===")
print(summary.to_string())

conn.close()
