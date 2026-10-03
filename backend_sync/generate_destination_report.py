import os, sys, json, time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from collections import Counter
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)
EXCEL_FILE = os.path.join(OUTPUT_DIR, "Bao_Cao_Diem_Den_Tiep_Theo_Forecast_Linehaul_BN.xlsx")

print("=== BUILDING COMPREHENSIVE DESTINATION FORECAST REPORT (FULL 12K ORDERS) ===")

# 1. Parse full 21 CTO sub-stations from Downloads file if exists, else fallback
dl_path1 = os.path.expanduser(r'~\Downloads\Danh sách khu vực trực thuộc.xlsx')
cto_stations = set()
cto_codes = set()
if os.path.exists(dl_path1):
    try:
        df_dl = pd.read_excel(dl_path1)
        for _, r in df_dl.iterrows():
            gd = str(r.get('Tên điểm GD', '')).strip().upper()
            nxt = str(r.get('Tên điểm tiếp theo', '')).strip().upper()
            m_nxt = str(r.get('Mã điểm tiếp theo', '')).strip().upper()
            if gd == 'CTO SC' and nxt not in ('BN HUB', 'HCM HUB'):
                cto_stations.add(nxt)
                cto_codes.add(m_nxt)
    except Exception as e:
        print(f"Note reading downloads: {e}")

cto_fallback = {
    'CT Ô MÔN', 'CT BÌNH THỦY', 'CT NINH KIỀU', 'DT CAO LÃNH', 'DT SA ĐÉC', 'CT LONG MỸ',
    'AG NHƠN HƯNG', 'CT THỚI AN', 'AG NÚI SAM', 'CT PHONG ĐIỀN', 'DT MỸ AN', 'AG CẦN ĐĂNG',
    'AG AN PHÚ', 'AG TÂN CHÂU', 'AG THOẠI SƠN', 'AG LONG XUYÊN', 'ST PHÚ LỢI', 'ST VĨNH CHÂU',
    'TG HÒA KHÁNH', 'TG AN HỮU', 'VL VĨNH LONG', 'CTO SC'
}
cto_stations.update(cto_fallback)
cto_codes.update({'CTC004A', 'CTC001H', 'CTC001D', 'CTC001A'})

# 2. Load 10,220 Forecast orders
fc_cache = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain", "3f5ffba4-bd34-4482-b10b-4d43e94be682", "scratch", "forecast_10209_extracted.json")
if os.path.exists(fc_cache):
    with open(fc_cache, 'r', encoding='utf-8') as f:
        fc_orders = json.load(f)
else:
    fc_orders = []

# 3. Load 1,908 BN Linehaul orders
bn_path = os.path.join(DATA_DIR, 'bn_linehaul_bills.json')
with open(bn_path, 'r', encoding='utf-8') as f:
    bn_orders = json.load(f)

# Load valid.csv for BN orders
VALID_FILE = os.path.join(BASE_DIR, 'backend_sync', 'config', 'valid.csv')
df_v = pd.read_csv(VALID_FILE, dtype=str)
df_v.columns = df_v.columns.str.strip()
dict_station, dict_area = {}, {}
for _, r in df_v.iterrows():
    st2 = str(r.get('Station_2') or r.get('Station_1') or '').strip()
    ar = str(r.get('area') or '').strip()
    st1 = str(r.get('Station_1') or '').strip().upper()
    if st1:
        dict_station[st1] = st2; dict_area[st1] = ar
    sc = str(r.get('sortcode') or '').strip().upper()
    if sc:
        dict_station[sc] = st2; dict_area[sc] = ar
        if len(sc) >= 6:
            dict_station[sc[:6]] = st2; dict_area[sc[:6]] = ar

def map_zone(area_val):
    if not area_val or area_val == 'Chưa gom':
        return 'Zone 3 (Tỉnh/Khác)'
    a = str(area_val).strip().upper()
    if a.startswith('A'): return 'Zone 1 (Nội thành)'
    if a.startswith('B'): return 'Zone 2 (Ngoại thành)'
    if a.startswith('C'): return 'Zone 3 (Miền Tây/Đông Nam)'
    if a.startswith('Z'): return 'Zone 5 (3PL)'
    return 'Zone 3 (Tỉnh/Khác)'

def is_cto(name, code):
    n = (name or '').strip().upper()
    c = (code or '').strip().upper()
    return n in cto_stations or c in cto_codes or n.startswith(('CT ', 'CTO '))

bn_processed = []
for b in bn_orders:
    next_name = str(b.get('nextNetworkName') or 'CHƯA XÁC ĐỊNH').strip()
    next_code = str(b.get('nextNetworkCode') or '').strip().upper()
    wt = float(b.get('weight') or b.get('countWeight') or 0.0)
    tc = str(b.get('parent_trace_code') or b.get('traceCode') or '').strip()
    plate = str(b.get('plate_number') or '').strip()
    
    name_up = next_name.upper()
    if is_cto(next_name, next_code):
        route = 'LH - CTO SC'
        ar = 'A05'
    elif 'DĨ AN' in name_up or 'DI AN' in name_up or next_code == 'HCM031A':
        route = 'LH - DC DĨ AN'
        ar = dict_area.get(next_code) or dict_area.get(name_up) or 'C06'
    elif (name_up.startswith('VT ') or next_code in ['HCM053A', 'HCM043A'] or 
          name_up.startswith('SETN') or next_code == 'TNI006M' or
          name_up.startswith('BD ') or name_up.startswith('DN ') or name_up.startswith('ĐN ') or
          'BÌNH DƯƠNG' in name_up or 'ĐỒNG NAI' in name_up):
        route = 'Shuttle - SE'
        ar = dict_area.get(next_code) or dict_area.get(name_up) or 'Chưa gom'
    else:
        route = 'Shuttle - HCM'
        ar = dict_area.get(next_code) or dict_area.get(name_up) or 'Chưa gom'

    zn = map_zone(ar)

    bn_processed.append({
        'Mã vận đơn': str(b.get('waybillNo') or b.get('billcode') or '').strip(),
        'Nguồn hàng': 'Linehaul BN HUB',
        'Trạng thái': 'Linehaul Arriving',
        'Biển số xe': plate,
        'Mã chuyến Linehaul': tc,
        'Bưu cục đích': next_name,
        'Mã trạm đích': next_code,
        'Máng gom Layout': ar,
        'Phân khu Zone': zn,
        'Tuyến chuyển tiếp': route,
        'Trọng lượng (kg)': round(wt, 2)
    })

fc_processed = []
for f in fc_orders:
    st_name = str(f.get('next_station') or '').strip()
    st_code = str(f.get('dispatch_code') or '').strip().upper()
    name_up = st_name.upper()
    
    if is_cto(st_name, st_code):
        route = 'LH - CTO SC'
        ar = 'A05'
    elif name_up.startswith(('BN ', 'HN ', 'HD ', 'HY ')) or 'BN HUB' in name_up:
        route = 'LH - BN HUB'
        ar = f.get('area_chute') or 'A06'
    elif 'DĨ AN' in name_up or 'DI AN' in name_up:
        route = 'LH - DC DĨ AN'
        ar = f.get('area_chute') or 'C06'
    elif (name_up.startswith('VT ') or name_up.startswith('SETN') or 
          name_up.startswith('BD ') or name_up.startswith('DN ') or name_up.startswith('ĐN ') or
          'BÌNH DƯƠNG' in name_up or 'ĐỒNG NAI' in name_up):
        route = 'Shuttle - SE'
        ar = f.get('area_chute') or 'Chưa gom'
    else:
        route = 'Shuttle - HCM'
        ar = f.get('area_chute') or 'Chưa gom'
        
    zn = map_zone(ar)
    fc_processed.append({
        'Mã vận đơn': f['tracking'],
        'Nguồn hàng': 'Pickup Forecast',
        'Trạng thái': f['status'],
        'Biển số xe': '',
        'Mã chuyến Linehaul': '',
        'Bưu cục đích': f['next_station'],
        'Mã trạm đích': st_code,
        'Máng gom Layout': ar,
        'Phân khu Zone': zn,
        'Tuyến chuyển tiếp': route,
        'Trọng lượng (kg)': f['weight_kg']
    })

all_orders = fc_processed + bn_processed
print(f"TOTAL ORDERS COMBINED: {len(all_orders):,}")

route_cnt = Counter()
route_wt = Counter()
for o in all_orders:
    route_cnt[o['Tuyến chuyển tiếp']] += 1
    route_wt[o['Tuyến chuyển tiếp']] += o['Trọng lượng (kg)']

zone_cnt = Counter()
zone_wt = Counter()
for o in all_orders:
    zone_cnt[o['Phân khu Zone']] += 1
    zone_wt[o['Phân khu Zone']] += o['Trọng lượng (kg)']

st_cnt = Counter()
st_wt = Counter()
for o in all_orders:
    st_cnt[o['Bưu cục đích']] += 1
    st_wt[o['Bưu cục đích']] += o['Trọng lượng (kg)']

with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
    df_route = pd.DataFrame([
        {'Tuyến Chuyển Tiếp': r, 'Số Lượng Đơn': c, 'Tỷ Lệ (%)': round(c/len(all_orders)*100, 2), 'Trọng Lượng (Tấn)': round(route_wt[r]/1000.0, 2)}
        for r, c in route_cnt.most_common()
    ])
    df_route.to_excel(writer, sheet_name='Tổng Hợp Tuyến', index=False)

    df_zone = pd.DataFrame([
        {'Zone Master': z, 'Số Lượng Đơn': c, 'Tỷ Lệ (%)': round(c/len(all_orders)*100, 2), 'Trọng Lượng (Tấn)': round(zone_wt[z]/1000.0, 2)}
        for z, c in zone_cnt.most_common()
    ])
    df_zone.to_excel(writer, sheet_name='Tổng Hợp Zone', index=False)

    df_top_st = pd.DataFrame([
        {'Bưu Cục Đích': s, 'Số Lượng Đơn': c, 'Tỷ Lệ (%)': round(c/len(all_orders)*100, 2), 'Trọng Lượng (Tấn)': round(st_wt[s]/1000.0, 2)}
        for s, c in st_cnt.most_common(50)
    ])
    df_top_st.to_excel(writer, sheet_name='Top 50 Bưu Cục Đích', index=False)

    pd.DataFrame(bn_processed).to_excel(writer, sheet_name='Chi Tiết 1908 BN Linehaul', index=False)
    pd.DataFrame(fc_processed).to_excel(writer, sheet_name='Chi Tiết 10220 Forecast', index=False)

print(f"✅ Báo cáo Excel hoàn tất: {EXCEL_FILE}")
