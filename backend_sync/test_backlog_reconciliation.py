import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Check latest records in backlog tables
df_sample = pd.read_sql("""
    SELECT billcode, bill_no, inventory_date, created_at
    FROM kpi_hub.backlog_live
    LIMIT 10;
""", conn)
print("\nSample backlog_live:")
print(df_sample.to_string())

# Check how many Inbound un-outbounded orders in enriched.dispatch_enriched exist in backlog
df_inb_unout = pd.read_sql("""
    SELECT 
        COUNT(*) as total_inbound_unoutbounded,
        COUNT(bl.billcode) as matched_in_backlog,
        COUNT(*) - COUNT(bl.billcode) as miss_outbound_not_in_backlog
    FROM enriched.dispatch_enriched de
    LEFT JOIN (
        SELECT DISTINCT COALESCE(billcode, bill_no) as billcode 
        FROM kpi_hub.backlog_live
    ) bl ON de.tracking = bl.billcode
    WHERE de.inbound_scandate IS NOT NULL
      AND de.outbound_scandate IS NULL;
""", conn)
print("\nReconciliation of Inbound un-outbounded with backlog_live:")
print(df_inb_unout.to_string())

# Check with raw_backlog as well
df_inb_unout_raw = pd.read_sql("""
    SELECT 
        COUNT(*) as total_inbound_unoutbounded,
        COUNT(bl.billcode) as matched_in_raw_backlog,
        COUNT(*) - COUNT(bl.billcode) as miss_outbound_not_in_raw_backlog
    FROM enriched.dispatch_enriched de
    LEFT JOIN (
        SELECT DISTINCT COALESCE(billcode, bill_no) as billcode 
        FROM kpi_hub.raw_backlog
    ) bl ON de.tracking = bl.billcode
    WHERE de.inbound_scandate IS NOT NULL
      AND de.outbound_scandate IS NULL;
""", conn)
print("\nReconciliation of Inbound un-outbounded with raw_backlog:")
print(df_inb_unout_raw.to_string())

conn.close()
