import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

# Load the 2,211 file
df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
file_wbs = set(str(x).strip() for x in df_2211['Mã vận đơn'])

# Load latest.json.gz (which has the 2,200 Linehaul orders from sync_postgre)
import gzip
with gzip.open('data/latest.json.gz', 'rt', encoding='utf-8') as f:
    dashboard_recs = json.load(f)

# Find all records in latest.json.gz that are in A06 / Linehaul
dash_linehaul_wbs = set()
for r in dashboard_recs:
    area = r.get('area_id') or r.get('area')
    st = r.get('station_name') or r.get('station')
    next_st = r.get('next_station')
    if area == 'A06' or st == 'BN HUB' or next_st == 'BN HUB':
        wb = str(r.get('tracking') or r.get('billcode') or '').strip()
        if wb:
            dash_linehaul_wbs.add(wb)

print(f"Total in Excel file: {len(file_wbs):,}")
print(f"Total in Dashboard Linehaul: {len(dash_linehaul_wbs):,}")

# The 11 missing orders:
missing_11 = file_wbs - dash_linehaul_wbs
print(f"\nExact missing count: {len(missing_11)}")

conn = get_pg_conn()
wbs_str = "('" + "','".join(missing_11) + "')"
df_miss = pd.read_sql(f"""
    SELECT 
        tracking,
        status_sys,
        operation_date_created,
        created_time,
        pickup_station,
        next_station,
        dispatch_code,
        orders_weight,
        round,
        rank,
        areacode,
        flowtypedesc,
        inbound_scandate,
        outbound_scandate
    FROM enriched.dispatch_enriched
    WHERE tracking IN {wbs_str}
""", conn)
conn.close()

print("\n--- CHI TIẾT 11 ĐƠN HÀNG LỆCH ---")
print(df_miss.to_string())

# Save to Excel & CSV for the user
df_miss.to_excel('DS_11_Don_Lech_Linehaul.xlsx', index=False)
print("\n✅ Saved to DS_11_Don_Lech_Linehaul.xlsx")
