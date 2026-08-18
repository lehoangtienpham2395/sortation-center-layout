import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

df_file = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
file_wbs = set(str(x).strip() for x in df_file['Mã vận đơn'])

conn = get_pg_conn()
df_db = pd.read_sql(f"""
    SELECT 
        tracking,
        status_sys,
        operation_date_created,
        created_time,
        pickup_station,
        next_station,
        dispatch_code,
        orders_weight,
        flag_pickup,
        flag_inbound,
        flag_outbound,
        inbound_scandate,
        outbound_scandate,
        is_rebound,
        operation_date_inbound,
        op_date_inbound_effective
    FROM enriched.dispatch_enriched
    WHERE tracking IN ({",".join("'" + str(x) + "'" for x in file_wbs)})
""", conn)

# Load Backlog set
df_bl = pd.read_sql("""
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
    UNION
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
""", conn)
backlog_set = set(str(x).strip() for x in df_bl['billcode'] if str(x).strip())
conn.close()

today = '2026-08-18'

# Test sync_postgre loop logic on these 2,211 orders
passed_orders = []
dropped_orders = []

for _, r in df_db.iterrows():
    wb = str(r['tracking']).strip()
    st_sys = str(r['status_sys'] or '').lower()
    
    # 1. Cancel check
    if any(kw in st_sys for kw in ['hủy', 'cancel', 'da huy']):
        dropped_orders.append((wb, 'Cancel', r))
        continue
        
    # 2. Backlog check
    has_in = bool(r['inbound_scandate'] or r['operation_date_inbound'] or r['op_date_inbound_effective'])
    has_out = bool(r['outbound_scandate'])
    is_reb = int(r['is_rebound'] or 0)
    
    is_inb_unout = (has_in or is_reb) and (not has_out)
    if is_inb_unout:
        ref_inb_date = str(r['op_date_inbound_effective'] or r['operation_date_inbound'] or r['operation_date_created'])[:10]
        if ref_inb_date < today and (wb not in backlog_set):
            dropped_orders.append((wb, 'Miss Outbound & Not in Backlog', r))
            continue
            
    passed_orders.append(wb)

print(f"Total in file: {len(file_wbs)}")
print(f"Passed in sync_postgre: {len(passed_orders)}")
print(f"Dropped in sync_postgre: {len(dropped_orders)}")

if dropped_orders:
    print("\n--- The 11 Dropped Orders Details ---")
    for wb, reason, r in dropped_orders:
        print(f"Tracking: {wb} | Reason: {reason} | status_sys: {r['status_sys']} | inb_date: {r['inbound_scandate']} | op_created: {r['operation_date_created']}")
