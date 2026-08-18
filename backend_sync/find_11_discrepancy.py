import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

# Load the 2,211 file
df_file = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
file_wbs = set(str(x).strip() for x in df_file['Mã vận đơn'])

# Load valid.csv
valid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'valid.csv')
df_val = pd.read_csv(valid_path, encoding='utf-8-sig')

dict_station, dict_area, dict_zone = {}, {}, {}
for _, r_v in df_val.iterrows():
    st1 = str(r_v.get('Station_1') or r_v.get('Tên bưu cục') or '').strip().upper()
    st2 = str(r_v.get('Station_2') or r_v.get('Tên điểm tiếp theo') or st1).strip().upper()
    ar  = str(r_v.get('area') or r_v.get('Mã khu vực') or '').strip().upper()
    zn  = str(r_v.get('Zone') or '').strip().upper()
    if st1:
        dict_station[st1] = st2; dict_area[st1] = ar; dict_zone[st1] = zn
    sc = str(r_v.get('sortcode') or '').strip().upper()
    if sc:
        dict_station[sc] = st2; dict_area[sc] = ar; dict_zone[sc] = zn
        if len(sc) >= 6:
            dict_station[sc[:6]] = st2; dict_area[sc[:6]] = ar; dict_zone[sc[:6]] = zn
    hub = str(r_v.get('Hubcode') or '').strip().upper()
    if hub and hub not in ('SR0001', 'SR0002'):
        dict_station[hub] = st2; dict_area[hub] = ar; dict_zone[hub] = zn
        if len(hub) >= 6:
            dict_station[hub[:6]] = st2; dict_area[hub[:6]] = ar; dict_zone[hub[:6]] = zn

conn = get_pg_conn()
wbs = "('" + "','".join(file_wbs) + "')"
df_db = pd.read_sql(f"""
    SELECT *
    FROM enriched.dispatch_enriched
    WHERE tracking IN {wbs}
""", conn)

# Load Backlog
df_bl = pd.read_sql("""
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
    UNION
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
""", conn)
backlog_set = set(str(x).strip() for x in df_bl['billcode'] if str(x).strip())
conn.close()

today = '2026-08-18'

in_linehaul_wbs = set()
out_of_linehaul = []

for _, r in df_db.iterrows():
    wb = str(r['tracking']).strip()
    st_sys_val = str(r.get('status_sys') or '').strip().lower()
    
    # 1. Cancel filter
    if any(kw in st_sys_val for kw in ['hủy', 'cancel', 'da huy']):
        out_of_linehaul.append((wb, 'Bị lọc HỦY', r))
        continue
        
    # 2. Backlog filter
    has_in = bool(r.get('inbound_scandate') or r.get('operation_date_inbound') or r.get('op_date_inbound_effective'))
    has_out = bool(r.get('outbound_scandate'))
    is_reb = int(r.get('is_rebound') or 0)
    
    is_inb_unout = (has_in or is_reb) and (not has_out)
    if is_inb_unout:
        ref_inb_date = str(r.get('op_date_inbound_effective') or r.get('operation_date_inbound') or r.get('operation_date_created'))[:10]
        if ref_inb_date < today and (wb not in backlog_set):
            out_of_linehaul.append((wb, 'Inbound ngày cũ không có trong Backlog', r))
            continue

    # 3. Area mapping
    target_st = str(r.get('next_station') or '').strip()
    target_st_upper = target_st.upper()
    sc = str(r.get('dispatch_code') or '').strip().upper()
    rk_raw = str(r.get('rank') or '').strip().upper()
    rd_raw = str(r.get('round') or '').strip().upper()
    
    is_north = (
        target_st_upper in ('BN HUB', 'HN SALE', 'HN HƯƠNG SƠN') or
        target_st_upper.startswith(('HN ', 'HD ', 'HY ', 'HP ', 'BN ', 'PT ', 'NB ', 'BG ', 'QN ', 'LS ', 'CB ', 'TQ ', 'YB ', 'SL ', 'DB ', 'HG ', 'ND ', 'VP ', 'TH ', 'NA ', 'HT ', 'HN', 'BN')) or
        dict_area.get(sc) == 'A06' or
        rk_raw == 'BN HUB' or
        rd_raw == 'LINEHAUL' or
        (sc and any(sc.upper().startswith(pfx) for pfx in ('HN', 'BN', 'HD', 'HY', 'HP', 'TB', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA', 'HNI', 'BNI', 'HPG', 'PTH', 'NBI')) and not sc.upper().startswith(('TNI', 'TNG')))
    )
    
    if is_north:
        in_linehaul_wbs.add(wb)
    else:
        out_of_linehaul.append((wb, f"Không map vào A06 (Next_st: '{target_st}', sc: '{sc}', round: '{rd_raw}', rank: '{rk_raw}')", r))

print(f"Tổng số đơn kiểm tra: {len(df_file):,}")
print(f"Số đơn vào Linehaul (A06): {len(in_linehaul_wbs):,}")
print(f"Số đơn KHÔNG vào Linehaul: {len(out_of_linehaul):,}")

if out_of_linehaul:
    print("\n--- CHI TIẾT CÁC ĐƠN KHÔNG VÀO LINEHAUL ---")
    for wb, reason, r in out_of_linehaul:
        print(f"Mã: {wb} | Lý do: {reason} | Next Station: {r.get('next_station')} | Pickup Station: {r.get('pickup_station')} | Dispatch Code: {r.get('dispatch_code')}")

    # Export to Excel & CSV without timezone issues
    df_out = pd.DataFrame([
        {
            'Mã vận đơn': wb,
            'Lý do không vào Linehaul': reason,
            'Trạng thái hệ thống': r.get('status_sys'),
            'Ngày tạo đơn': str(r.get('operation_date_created')),
            'Bưu cục gửi': r.get('pickup_station'),
            'Điểm tiếp theo': r.get('next_station'),
            'Mã điều phối': r.get('dispatch_code'),
            'Khối lượng tính cước (Kg)': float(r.get('orders_weight') or 0),
            'Round': r.get('round'),
            'Rank': r.get('rank')
        }
        for wb, reason, r in out_of_linehaul
    ])
    df_out.to_excel('DS_11_Don_Khong_Vao_Linehaul.xlsx', index=False)
    df_out.to_csv('DS_11_Don_Khong_Vao_Linehaul.csv', index=False, encoding='utf-8-sig')
    print("\n✅ Đã lưu file: DS_11_Don_Khong_Vao_Linehaul.xlsx & DS_11_Don_Khong_Vao_Linehaul.csv")
