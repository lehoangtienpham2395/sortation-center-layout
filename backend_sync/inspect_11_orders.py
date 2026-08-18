import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn, load_valid_csv, OFFICIAL_LAYOUT_MAP
import pandas as pd

# 1. Load the 2,211 exported orders
df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
print(f"Total exported orders: {len(df_2211)}")

# 2. Check valid.csv paths and contents
for p in [
    r'backend_sync\config\valid.csv',
    r'config\valid.csv',
    r'data\valid.csv',
    r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv',
    r'C:\Users\lehoa\OneDrive\Desktop\testing\config\valid.csv'
]:
    if os.path.exists(p):
        print(f"Found valid.csv at: {p} (mtime: {os.path.getmtime(p)}, lines: {sum(1 for _ in open(p, encoding='utf-8-sig', errors='ignore'))})")

# 3. Load latest valid map
valid_map = load_valid_csv()
print(f"Total valid mappings: {len(valid_map)}")

# 4. Check how each of the 2,211 orders is classified by sync_postgre logic
conn = get_pg_conn()
today = '2026-08-18'
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
        round,
        rank,
        areacode,
        flowtypedesc
    FROM enriched.dispatch_enriched
    WHERE tracking IN ({",".join("'" + str(x) + "'" for x in df_2211['Mã vận đơn'])})
""", conn)
conn.close()

print(f"Found in DB: {len(df_db)}")

# Classify each order into Chute / Round
classified = []
for _, r in df_db.iterrows():
    wb = str(r['tracking']).strip()
    next_st = str(r['next_station'] or '').strip().upper()
    pk_st = str(r['pickup_station'] or '').strip().upper()
    sc = str(r['dispatch_code'] or '').strip().upper()
    rd_val = str(r['round'] or '').strip().upper()
    rk_val = str(r['rank'] or '').strip().upper()
    
    # Check valid map lookup
    st_info = valid_map.get(sc) or valid_map.get(next_st)
    if st_info:
        station, zone, area_id = st_info
    else:
        station = next_st
        zone = '1'
        area_id = 'A06'
        
    is_linehaul_a06 = (area_id == 'A06' or station == 'BN HUB' or next_st == 'BN HUB')
    classified.append({
        'tracking': wb,
        'next_station': next_st,
        'pickup_station': pk_st,
        'dispatch_code': sc,
        'mapped_station': station,
        'mapped_zone': zone,
        'mapped_area_id': area_id,
        'round': rd_val,
        'rank': rk_val,
        'is_linehaul_a06': is_linehaul_a06
    })

df_cls = pd.DataFrame(classified)
not_in_a06 = df_cls[~df_cls['is_linehaul_a06']]
print(f"\nTotal classified: {len(df_cls)}")
print(f"Classified into A06 / Linehaul: {df_cls['is_linehaul_a06'].sum()}")
print(f"NOT classified into A06 / Linehaul: {len(not_in_a06)}")

if len(not_in_a06) > 0:
    print("\n--- The 11 orders NOT in Linehaul / A06 ---")
    print(not_in_a06.to_string())

# Also check if the 11 orders are from round/rank or dispatch_code mapping
print("\n--- Breakdown by mapped_area_id ---")
print(df_cls['mapped_area_id'].value_counts())

print("\n--- Breakdown by round ---")
print(df_cls['round'].value_counts())
