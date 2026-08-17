import re
import pandas as pd
import json

user_list_text = """
B19	SG BÌNH LỢI,SG MINH XUÂN
B20	LA ĐỨC HÒA
B18	SG HÓC MÔN
B04	SG TÂN THỚI HIỆP
A06	BN HUB
A19	AG LONG XUYÊN
B17	SG HƯNG LONG
B00	SG CHỢ LỚN
C25	LA BẾN LỨC
C11	LA CẦN ĐƯỚC
A20	AG CẦN ĐĂNG
C27	DN TRẢNG BOM
B16	SG BÀ ĐIỂM
C26	SETN
C22	VT LONG ĐẤT
C12	SG PHÚ NHUẬN
B10	SG GÒ VẤP
A16	SG THỦ ĐỨC
C09	LA HẬU NGHĨA
C08	TG GÒ CÔNG
C10	SG XUÂN HÒA
C24	BD BÌNH HÒA
B06	SG HIỆP BÌNH
B13	VT XUYÊN MỘC
B12	VT CHÂU ĐỨC
C23	SG BẢY HIỀN
C16	SG NHƠN ĐỨC
C21	AG THOẠI SƠN
C20	AG TỊNH BIÊN
C19	AG TÂN CHÂU
C18	AG AN PHÚ
C17	VL CHỢ LÁCH
C15	ST PHÚ LỢI
C14	CT LONG MỸ
C13	ST VĨNH CHÂU
C07	DC GIA ĐỊNH
C06	BD DĨ AN
C05	SG KHÁNH HỘI
A18	VT VŨNG TÀU
A17	TG TRUNG AN
A14	TG AN HỮU
A12	TG HÒA KHÁNH
A10	DT CAO LÃNH
A09	CT NINH KIỀU
A08	CT BÌNH THỦY
A07	CT Ô MÔN
C04	SG BÌNH TRỊ ĐÔNG
C03	SG BÌNH LỢI TRUNG
B09	SG TÂN TẠO
B03	SG BÌNH TÂN
A15	LA TÂN AN
A13	VL VĨNH LONG
A11	DT SA ĐÉC
B15	SG TÂN NHỰT
B14	SG VĨNH LỘC
B11	SG AN PHÚ ĐÔNG
B08	SG CỦ CHI
B07	SG TÂN SƠN NHÌ
B05	SG PHÚ LÂM
B02	SG TÂN HƯNG
B01	SG ĐÔNG HƯNG THUẬN
"""

user_dict = {}
for line in user_list_text.strip().split('\n'):
    line = line.strip()
    if not line:
        continue
    if '\t' in line:
        code, st = line.split('\t', 1)
        user_dict[code.strip()] = st.strip()
    elif ' ' in line:
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            user_dict[parts[0].strip()] = parts[1].strip()

print(f"Total areas in user list: {len(user_dict)}")

# Read App.tsx
with open('src/App.tsx', 'r', encoding='utf-8') as f:
    app_code = f.read()

# Extract MASTER_CONFIG_MAP
app_map = {}
m = re.search(r'const MASTER_CONFIG_MAP: Record<string, string> = \{([\s\S]*?)\};', app_code)
if m:
    lines = m.group(1).split('\n')
    for l in lines:
        l = l.strip()
        if ':' in l:
            k, v = l.split(':', 1)
            k = k.strip().strip("'\"")
            v = v.strip().rstrip(",").strip("'\"")
            if k:
                app_map[k] = v

print(f"Total in App.tsx MASTER_CONFIG_MAP: {len(app_map)}")

# Extract ZONE1_LIST, ZONE2_LIST, ZONE3_LIST
zone_items = {}
for z_name in ['ZONE1_LIST', 'ZONE2_LIST', 'ZONE3_LIST']:
    m_z = re.search(rf'const {z_name}: [^=]+ = \[([\s\S]*?)\];', app_code)
    if m_z:
        items_text = m_z.group(1)
        for obj in re.finditer(r'\{[^}]+\}', items_text):
            obj_str = obj.group(0)
            m_id = re.search(r'areaId:\s*[\'"]([^\'"]+)[\'"]', obj_str)
            m_name = re.search(r'name:\s*[\'"]([^\'"]+)[\'"]', obj_str)
            m_zone = re.search(r'zone:\s*(\d+)', obj_str)
            if m_id and m_name:
                zone_items[m_id.group(1)] = {
                    'name': m_name.group(1),
                    'zone': m_zone.group(1) if m_zone else ''
                }

print(f"Total in App.tsx Zone Lists: {len(zone_items)}")

# Read valid.csv
df_v = pd.read_csv('backend_sync/config/valid.csv', dtype=str)
valid_area_stations = {}
for _, r in df_v.iterrows():
    ar = str(r.get('area') or '').strip()
    st = str(r.get('Station_2') or '').strip()
    if ar:
        if ar not in valid_area_stations:
            valid_area_stations[ar] = set()
        if st:
            valid_area_stations[ar].add(st)

# Print comparison
print("\n" + "="*80)
print(f"{'Area':<6} | {'User Station':<30} | {'App.tsx MAP':<25} | {'App.tsx Zone':<20} | {'Status'}")
print("="*80)

diff_count = 0
for code in sorted(user_dict.keys()):
    user_st = user_dict[code]
    app_st = app_map.get(code, 'MISSING')
    z_item = zone_items.get(code, {})
    z_name = z_item.get('name', 'MISSING')
    z_num = z_item.get('zone', '')
    
    is_match = (user_st == app_st) and (user_st == z_name or (',' in user_st and (user_st in z_name or z_name in user_st)))
    status = "✅ MATCH" if is_match else "❌ DIFF"
    if not is_match:
        diff_count += 1
    print(f"{code:<6} | {user_st:<30} | {app_st:<25} | {z_name:<20} | {status}")

print("\n" + "="*80)
print(f"Total discrepancies: {diff_count}")
