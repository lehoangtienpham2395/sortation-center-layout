import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# Check raw_dispatch / raw_backlog for cancelled records
for tbl in ['kpi_hub.raw_backlog', 'kpi_hub.backlog_live', 'kpi_hub.raw_order', 'kpi_hub.raw_order_live']:
    try:
        q = f"""
            SELECT count(*) as total_canceled
            FROM {tbl}
            WHERE waybill_status ILIKE '%hủy%' OR waybill_status ILIKE '%cancel%'
               OR abnormal_remark ILIKE '%hủy%' OR abnormal_remark ILIKE '%cancel%';
        """
        res = pd.read_sql(q, conn)
        print(f"Table {tbl} cancellations: {res.iloc[0]['total_canceled']}")
    except Exception as e:
        print(f"Error {tbl}: {e}")

conn.close()
