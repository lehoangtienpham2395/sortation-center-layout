import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()
df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
wbs = "('" + "','".join(str(x) for x in df_2211['Mã vận đơn']) + "')"
df_db = pd.read_sql(f"SELECT tracking, next_station, pickup_station, dispatch_code, round, rank FROM enriched.dispatch_enriched WHERE tracking IN {wbs}", conn)
conn.close()

count_a06 = 0
not_a06 = []
for _, r in df_db.iterrows():
    next_st = str(r['next_station'] or '').strip().upper()
    sc = str(r['dispatch_code'] or '').strip().upper()
    rk = str(r['rank'] or '').strip().upper()
    rd = str(r['round'] or '').strip().upper()
    
    is_north = (
        next_st in ('BN HUB', 'HN SALE', 'HN HƯƠNG SƠN') or
        next_st.startswith(('HN ', 'HD ', 'HY ', 'HP ', 'BN ', 'PT ', 'NB ', 'BG ', 'QN ', 'LS ', 'CB ', 'TQ ', 'YB ', 'SL ', 'DB ', 'HG ', 'ND ', 'VP ', 'TH ', 'NA ', 'HT ', 'HN', 'BN')) or
        rk == 'BN HUB' or
        rd == 'LINEHAUL' or
        (sc and any(sc.startswith(pfx) for pfx in ('HN', 'BN', 'HD', 'HY', 'HP', 'TB', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA', 'HNI', 'BNI', 'HPG', 'PTH', 'NBI')) and not sc.startswith(('TNI', 'TNG')))
    )
    if is_north:
        count_a06 += 1
    else:
        not_a06.append(r)

print(f"Total tested: {len(df_db)}")
print(f"Mapped to A06 / Linehaul: {count_a06}")
print(f"Not mapped to A06: {len(not_a06)}")
if not_a06:
    print("Sample not mapped:", not_a06[:5])
