import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

# Load the 2,211 exported orders
df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
print(f"Total exported orders: {len(df_2211)}")

# Load valid.csv
valid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'valid.csv')
print(f"Loading valid.csv from: {valid_path}")
df_val = pd.read_csv(valid_path, encoding='utf-8-sig')

dict_station, dict_area, dict_zone = {}, {}, {}
for _, r_v in df_val.iterrows():
    st1 = str(r_v.get('Tên bưu cục') or '').strip().upper()
    st2 = str(r_v.get('Tên điểm tiếp theo') or st1).strip().upper()
    ar  = str(r_v.get('Mã khu vực') or '').strip().upper()
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

OFFICIAL_LAYOUT_MAP = {
    'A06': ('BN HUB', '1'), 'A07': ('CT Ô MÔN', '1'), 'A08': ('CT BÌNH THỦY', '1'),
    'A09': ('CT NINH KIỀU', '1'), 'A10': ('DT CAO LÃNH', '1'), 'A11': ('DT SA ĐÉC', '1'),
    'A12': ('TG HÒA KHÁNH', '1'), 'A13': ('VL VĨNH LONG', '1'), 'A14': ('TG AN HỮU', '1'),
    'A15': ('LA TÂN AN', '1'), 'A16': ('SG THỦ ĐỨC', '1'), 'A17': ('TG TRUNG AN', '1'),
    'A18': ('VT VŨNG TÀU', '1'), 'A19': ('AG LONG XUYÊN', '1'), 'A20': ('AG CẦN ĐĂNG', '1'),
    'B00': ('SG CHỢ LỚN', '2'), 'B01': ('SG TÂN BÌNH', '2'), 'B02': ('SG BÌNH THẠNH', '2'),
    'B03': ('SG QUẬN 7', '2'), 'B04': ('SG TÂN THỚI HIỆP', '2'), 'B05': ('SG TÂN TẠO', '2'),
    'B06': ('SG HIỆP BÌNH', '2'), 'B07': ('SG QUẬN 10', '2'), 'B08': ('SG QUẬN 12', '2'),
    'B09': ('SG PHÚ LÂM', '2'), 'B10': ('SG GÒ VẤP', '2'), 'B11': ('BD THUẬN AN', '2'),
    'B12': ('VT CHÂU ĐỨC', '2'), 'B13': ('VT XUYÊN MỘC', '2'), 'B14': ('SG LINH XUÂN', '2'),
    'B15': ('SG BÌNH CHÁNH', '2'), 'B16': ('SG BÀ ĐIỂM', '2'), 'B17': ('SG HƯNG LONG', '2'),
    'B18': ('SG HÓC MÔN', '2'), 'B19': ('SG BÌNH LỢI,SG MINH XUÂN', '2'), 'B20': ('LA ĐỨC HÒA', '2'),
    'C03': ('SG ĐÔNG HƯNG THUẬN', '3'), 'C04': ('SG BÌNH TÂN', '3'), 'C05': ('SG KHÁNH HỘI', '3'),
    'C06': ('BD DĨ AN', '3'), 'C07': ('DC GIA ĐỊNH', '3'), 'C08': ('TG GÒ CÔNG', '3'),
    'C09': ('LA HẬU NGHĨA', '3'), 'C10': ('SG XUÂN HÒA', '3'), 'C11': ('LA CẦN ĐƯỚC', '3'),
    'C12': ('SG PHÚ NHUẬN', '3'), 'C13': ('ST VĨNH CHÂU', '3'), 'C14': ('CT LONG MỸ', '3'),
    'C15': ('ST PHÚ LỢI', '3'), 'C16': ('SG NHƠN ĐỨC', '3'), 'C17': ('VL CHỢ LÁCH', '3'),
    'C18': ('AG AN PHÚ', '3'), 'C19': ('AG TÂN CHÂU', '3'), 'C20': ('AG TỊNH BIÊN', '3'),
    'C21': ('AG THOẠI SƠN', '3'), 'C22': ('VT LONG ĐẤT', '3'), 'C23': ('SG BẢY HIỀN', '3'),
    'C24': ('BD BÌNH HÒA', '3'), 'C25': ('LA BẾN LỨC', '3'), 'C26': ('SETN', '3'),
    'C27': ('DN TRẢNG BOM', '3'),
}
OFFICIAL_NAME_TO_CHUTE = {}
for _cid, (_cname, _czone) in OFFICIAL_LAYOUT_MAP.items():
    OFFICIAL_NAME_TO_CHUTE[_cname.upper()] = (_cid, _czone)
    for _sub in _cname.upper().split(','):
        if _sub.strip():
            OFFICIAL_NAME_TO_CHUTE[_sub.strip()] = (_cid, _czone)

conn = get_pg_conn()
wbs = "('" + "','".join(str(x) for x in df_2211['Mã vận đơn']) + "')"
df_db = pd.read_sql(f"""
    SELECT tracking, next_station, pickup_station, dispatch_code, round, rank, status_sys, operation_date_created
    FROM enriched.dispatch_enriched
    WHERE tracking IN {wbs}
""", conn)
conn.close()

not_linehaul_orders = []

for _, r in df_db.iterrows():
    wb = str(r['tracking']).strip()
    next_st = str(r['next_station'] or '').strip().upper()
    sc = str(r['dispatch_code'] or '').strip().upper()
    pk = str(r['pickup_station'] or '').strip().upper()
    
    # Mapping logic from sync_postgre.py
    station = dict_station.get(sc) or dict_station.get(next_st) or next_st
    area_id = dict_area.get(sc) or dict_area.get(next_st) or ''
    zone    = dict_zone.get(sc) or dict_zone.get(next_st) or ''
    
    if area_id in OFFICIAL_LAYOUT_MAP:
        off_name, off_zone = OFFICIAL_LAYOUT_MAP[area_id]
        station = off_name
        zone    = off_zone
    elif station in OFFICIAL_NAME_TO_CHUTE:
        off_id, off_zone = OFFICIAL_NAME_TO_CHUTE[station]
        area_id = off_id
        zone    = off_zone
        station = OFFICIAL_LAYOUT_MAP[off_id][0]
    elif next_st in OFFICIAL_NAME_TO_CHUTE:
        off_id, off_zone = OFFICIAL_NAME_TO_CHUTE[next_st]
        area_id = off_id
        zone    = off_zone
        station = OFFICIAL_LAYOUT_MAP[off_id][0]
        
    is_linehaul = (area_id == 'A06' or station == 'BN HUB')
    if not is_linehaul:
        not_linehaul_orders.append({
            'tracking': wb,
            'next_station': next_st,
            'pickup_station': pk,
            'dispatch_code': sc,
            'resolved_station': station,
            'resolved_area_id': area_id,
            'resolved_zone': zone,
            'round': r['round'],
            'rank': r['rank'],
            'status_sys': r['status_sys']
        })

df_not = pd.DataFrame(not_linehaul_orders)
print(f"\n📊 Tổng số đơn trong file: {len(df_db)}")
print(f"📦 Số đơn được map vào A06 / Linehaul: {len(df_db) - len(df_not)}")
print(f"⚠️ Số đơn KHÔNG nằm trong A06 / Linehaul ({len(df_not)} đơn):")
print(df_not.to_string())
