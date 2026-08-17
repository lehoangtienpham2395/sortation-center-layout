import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

import pandas as pd
from sync_postgre import get_pg_conn, VALID_FILE

# Load sortcode to area mapping from valid.csv
df_v = pd.read_csv(VALID_FILE, dtype=str)
dict_area = {}
dict_station = {}
for _, r_v in df_v.iterrows():
    sc = str(r_v.get('sortcode') or '').strip().upper()
    ar = str(r_v.get('area') or '').strip()
    st2 = str(r_v.get('Station_2') or '').strip()
    if sc:
        dict_area[sc] = ar
        dict_station[sc] = st2
        if len(sc) >= 6:
            dict_area[sc[:6]] = ar
            dict_station[sc[:6]] = st2

conn = get_pg_conn()
df = pd.read_sql("""
    SELECT 
        tracking AS "Mã vận đơn (Tracking)",
        operation_date_created AS "Ngày ca tạo đơn",
        created_time AS "Thời gian tạo đơn",
        pickup_station AS "Bưu cục gửi (Pickup Station)",
        next_station AS "Trạm đích (Next Station)",
        dispatch_code AS "Mã phân vùng (Dispatch Code)",
        area_id AS "Chute_Gốc",
        status_sys AS "Trạng thái hệ thống",
        orders_num AS "Số kiện",
        orders_weight AS "Trọng lượng cước (kg)",
        ROUND((orders_weight / 1000.0)::numeric, 4) AS "Trọng lượng (Tấn)",
        pickup_time AS "Thời gian lấy hàng",
        arrival_scandate AS "Thời gian xe đến cảng",
        inbound_scandate AS "Thời gian nhập kho (Inbound)",
        outbound_scandate AS "Thời gian xuất kho (Outbound)",
        flag_pickup AS "Cờ lấy hàng",
        flag_arrival AS "Cờ đến cảng",
        flag_inbound AS "Cờ nhập kho",
        flag_outbound AS "Cờ xuất kho"
    FROM enriched.dispatch_enriched
    WHERE 
        operation_date_created >= ('2026-08-17'::date - INTERVAL '15 days')
        AND outbound_scandate IS NULL
    ORDER BY operation_date_created DESC, created_time DESC;
""", conn)
conn.close()

is_a06_list = []
for _, r in df.iterrows():
    sc = str(r.get("Mã phân vùng (Dispatch Code)") or '').strip().upper()
    nxt = str(r.get("Trạm đích (Next Station)") or '').strip().upper()
    ar_orig = str(r.get("Chute_Gốc") or '').strip().upper()
    
    ar_mapped = dict_area.get(sc, '')
    if not ar_mapped and len(sc) >= 6:
        ar_mapped = dict_area.get(sc[:6], '')
        
    is_north = bool(
        nxt == 'BN HUB' or
        nxt.startswith(('HN ', 'HD ', 'HY ', 'HP ', 'BN ', 'PT ', 'NB ', 'BG ', 'QN ', 'LS ', 'CB ', 'TQ ', 'YB ', 'SL ', 'DB ', 'HG ', 'ND ', 'VP ', 'TH ', 'NA ', 'HT ')) or
        ar_mapped == 'A06' or
        ar_orig == 'A06' or
        (sc and any(sc.startswith(pfx) for pfx in ('HN', 'BN', 'HD', 'HY', 'HP', 'TB', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA')) and not sc.startswith(('TNI', 'TNG')))
    )
    is_a06_list.append(is_north)

df['is_a06'] = is_a06_list
df_a06 = df[df['is_a06'] == True].copy()
df_a06['Chute / Máng'] = 'A06'
df_a06.drop(columns=['is_a06', 'Chute_Gốc'], inplace=True)

# Datetime tz conversion
for col in df_a06.columns:
    if pd.api.types.is_datetime64_any_dtype(df_a06[col]):
        df_a06[col] = df_a06[col].astype(str)

root_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
excel_path = os.path.join(root_dir, 'DS_Don_BN_HUB_Chua_Outbound_3097.xlsx')
csv_path = os.path.join(root_dir, 'DS_Don_BN_HUB_Chua_Outbound_3097.csv')

df_a06.to_excel(excel_path, index=False, engine='openpyxl')
df_a06.to_csv(csv_path, index=False, encoding='utf-8-sig')

total_kg = df_a06['Trọng lượng cước (kg)'].sum()
print(f"✅ Đã xuất {len(df_a06)} dòng dữ liệu:")
print(f"   - File Excel: {excel_path}")
print(f"   - File CSV:   {csv_path}")
print(f"   - Tổng trọng lượng: {total_kg:,.2f} kg ({total_kg/1000:,.3f} Tấn)")
