import re
import pandas as pd

user_list = [
    ("B19", "SG BÌNH LỢI,SG MINH XUÂN"),
    ("B20", "LA ĐỨC HÒA"),
    ("B18", "SG HÓC MÔN"),
    ("B04", "SG TÂN THỚI HIỆP"),
    ("A06", "BN HUB"),
    ("A19", "AG LONG XUYÊN"),
    ("B17", "SG HƯNG LONG"),
    ("B00", "SG CHỢ LỚN"),
    ("C25", "LA BẾN LỨC"),
    ("C11", "LA CẦN ĐƯỚC"),
    ("A20", "AG CẦN ĐĂNG"),
    ("C27", "DN TRẢNG BOM"),
    ("B16", "SG BÀ ĐIỂM"),
    ("C26", "SETN"),
    ("C22", "VT LONG ĐẤT"),
    ("C12", "SG PHÚ NHUẬN"),
    ("B10", "SG GÒ VẤP"),
    ("A16", "SG THỦ ĐỨC"),
    ("C09", "LA HẬU NGHĨA"),
    ("C08", "TG GÒ CÔNG"),
    ("C10", "SG XUÂN HÒA"),
    ("C24", "BD BÌNH HÒA"),
    ("B06", "SG HIỆP BÌNH"),
    ("B13", "VT XUYÊN MỘC"),
    ("B12", "VT CHÂU ĐỨC"),
    ("C23", "SG BẢY HIỀN"),
    ("C16", "SG NHƠN ĐỨC"),
    ("C21", "AG THOẠI SƠN"),
    ("C20", "AG TỊNH BIÊN"),
    ("C19", "AG TÂN CHÂU"),
    ("C18", "AG AN PHÚ"),
    ("C17", "VL CHỢ LÁCH"),
    ("C15", "ST PHÚ LỢI"),
    ("C14", "CT LONG MỸ"),
    ("C13", "ST VĨNH CHÂU"),
    ("C07", "DC GIA ĐỊNH"),
    ("C06", "BD DĨ AN"),
    ("C05", "SG KHÁNH HỘI"),
    ("A18", "VT VŨNG TÀU"),
    ("A17", "TG TRUNG AN"),
    ("A14", "TG AN HỮU"),
    ("A12", "TG HÒA KHÁNH"),
    ("A10", "DT CAO LÃNH"),
    ("A09", "CT NINH KIỀU"),
    ("A08", "CT BÌNH THỦY"),
    ("A07", "CT Ô MÔN"),
    ("C04", "SG BÌNH TRỊ ĐÔNG"),
    ("C03", "SG BÌNH LỢI TRUNG"),
    ("B09", "SG TÂN TẠO"),
    ("B03", "SG BÌNH TÂN"),
    ("A15", "LA TÂN AN"),
    ("A13", "VL VĨNH LONG"),
    ("A11", "DT SA ĐÉC"),
    ("B15", "SG TÂN NHỰT"),
    ("B14", "SG VĨNH LỘC"),
    ("B11", "SG AN PHÚ ĐÔNG"),
    ("B08", "SG CỦ CHI"),
    ("B07", "SG TÂN SƠN NHÌ"),
    ("B05", "SG PHÚ LÂM"),
    ("B02", "SG TÂN HƯNG"),
    ("B01", "SG ĐÔNG HƯNG THUẬN"),
]

user_dict = {code.strip(): st.strip() for code, st in user_list}

# Load App.tsx static definitions
with open('src/App.tsx', 'r', encoding='utf-8') as f:
    app_text = f.read()

# Load valid.csv
df_v = pd.read_csv('backend_sync/config/valid.csv', dtype=str)
valid_map = {}
for _, r in df_v.iterrows():
    ar = str(r.get('area') or '').strip()
    st = str(r.get('Station_2') or '').strip()
    if ar and st:
        if ar not in valid_map:
            valid_map[ar] = set()
        valid_map[ar].add(st)

# Load layout definitions from App.tsx
def parse_zone_list(list_name):
    pattern = rf'const {list_name} = \[([\s\S]*?)\];'
    m = re.search(pattern, app_text)
    items = {}
    if m:
        for match in re.finditer(r"areaId:\s*'([^']+)',\s*name:\s*'([^']+)'", m.group(1)):
            items[match.group(1)] = match.group(2)
    return items

z3 = parse_zone_list('ZONE3_LIST')
z2 = parse_zone_list('ZONE2_LIST')
z1 = parse_zone_list('ZONE1_LIST')

all_app_chutes = {}
all_app_chutes.update(z3)
all_app_chutes.update(z2)
all_app_chutes.update(z1)

report = []
for code, user_st in sorted(user_dict.items()):
    app_st = all_app_chutes.get(code, 'CHƯA CÓ TRÊN LAYOUT')
    v_st = ', '.join(sorted(valid_map.get(code, []))) or 'CHƯA CÓ TRONG valid.csv'
    
    # Check match
    matched = False
    if code in all_app_chutes:
        if user_st == app_st:
            matched = True
        elif ',' in user_st and all(part.strip() in app_st for part in user_st.split(',')):
            matched = True
        elif ',' in app_st and all(part.strip() in user_st for part in app_st.split(',')):
            matched = True
            
    report.append({
        'code': code,
        'user_station': user_st,
        'app_station': app_st,
        'valid_station': v_st,
        'matched': matched
    })

# Write markdown report
with open('layout_comparison_report.md', 'w', encoding='utf-8') as f:
    f.write("# BÁO CÁO ĐỐI SOÁT ZONE & TÊN BƯU CỤC TRÊN LAYOUT\n\n")
    f.write(f"Tổng số máng/chute yêu cầu: **{len(user_dict)}**\n\n")
    
    diffs = [r for r in report if not r['matched']]
    matches = [r for r in report if r['matched']]
    
    f.write(f"- Khớp hoàn toàn: **{len(matches)} / {len(user_dict)}**\n")
    f.write(f"- Điểm khác biệt / Cần cập nhật: **{len(diffs)} / {len(user_dict)}**\n\n")
    
    if diffs:
        f.write("## ⚠️ DANH SÁCH CÁC VỊ TRÍ CẦN ĐIỀU CHỈNH / CẬP NHẬT\n\n")
        f.write("| Mã khu vực | Tên điểm mới yêu cầu | Tên hiện tại trong App.tsx Layout | Tên trong valid.csv |\n")
        f.write("| :---: | :--- | :--- | :--- |\n")
        for r in diffs:
            f.write(f"| **{r['code']}** | `{r['user_station']}` | `{r['app_station']}` | `{r['valid_station']}` |\n")
        f.write("\n")
        
    f.write("## ✅ DANH SÁCH CÁC VỊ TRÍ ĐÃ KHỚP HOÀN TOÀN\n\n")
    f.write("| Mã khu vực | Tên điểm bưu cục | Trạng thái |\n")
    f.write("| :---: | :--- | :---: |\n")
    for r in matches:
        f.write(f"| **{r['code']}** | {r['user_station']} | ✅ Khớp |\n")

print(f"Report generated: {len(matches)} matches, {len(diffs)} differences.")
