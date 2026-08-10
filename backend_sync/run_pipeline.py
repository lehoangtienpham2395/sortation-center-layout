import os
import sys
import glob
import json
import time
import requests
import threading
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Thiết lập encoding UTF-8 cho console
try:
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Import module đăng nhập dùng chung
from auth import get_valid_token, handle_401

# ============================================================
# CONFIG
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INCOMING_DIR = os.path.join(BASE_DIR, "Exportauto", "IncomingCargo")
VALID_DIR = os.path.join(BASE_DIR, "Exportauto", "Valid")

# Tạo thư mục xuất dữ liệu nếu chưa có
os.makedirs(INCOMING_DIR, exist_ok=True)

# Đọc cấu hình từ các file JSON hiện có
SHUTTLE_HEADERS_FILE = os.path.join(BASE_DIR, "report_shuttleheaders.json")
SHUTTLE_PAYLOAD_FILE = os.path.join(BASE_DIR, "report_shuttlepayload.json")
LINEHAUL_HEADERS_FILE = os.path.join(BASE_DIR, "report_linehaulheaders.json")
LINEHAUL_PAYLOAD_FILE = os.path.join(BASE_DIR, "report_linehaulpayload.json")
INCOMING_HEADERS_FILE = os.path.join(BASE_DIR, "incoming_cargoheaders.json")
INCOMING_PAYLOAD_FILE = os.path.join(BASE_DIR, "incoming_cargopayload.json")

# Khoảng thời gian lọc (7 ngày gần nhất)
now = datetime.now()
START_TIME = (now - timedelta(days=6)).strftime('%Y-%m-%d') + " 00:00:00"
END_TIME = now.strftime('%Y-%m-%d') + " 23:59:59"

print("=======================================================")
print("🚀 HỆ THỐNG PIPELINE GIÁM SÁT HÀNG ĐẾN HCM HUB (7 NGÀY)")
print("=======================================================")
print(f"📅 Khoảng thời gian: {START_TIME} ➔ {END_TIME}")

# ============================================================
# CÁC HÀM CRAWLER DỮ LIỆU
# ============================================================

def set_token(headers, token):
    headers = headers.copy()
    headers['authToken'] = token
    headers['Authtoken'] = token
    return headers

def load_json_config(headers_path, payload_path):
    with open(headers_path, 'r', encoding='utf-8') as f:
        headers = json.load(f)
    with open(payload_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    return headers, payload

def pull_shuttle(token):
    print("\n🚚 [1/4] Đang tải dữ liệu Trung chuyển Shuttle từ J&T...")
    headers, payload = load_json_config(SHUTTLE_HEADERS_FILE, SHUTTLE_PAYLOAD_FILE)
    headers = set_token(headers, token)
    
    url = 'https://gw.jtcargo.com.vn/transportation/tmsBranchTrackingDetail/page'
    
    payload['startDepartureTime'] = START_TIME
    payload['endDepartureTime'] = END_TIME
    payload['size'] = 200
    
    all_data = []
    current_page = 1
    
    while True:
        print(f"   Trang {current_page}...", end=' ', flush=True)
        payload['current'] = current_page
        
        page_list = None
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=30)
                if r.status_code in [401, 405] or r.json().get('code') in [401, 405]:
                    headers, new_token = handle_401(headers)
                    headers = set_token(headers, new_token)
                    r = requests.post(url, headers=headers, json=payload, timeout=30)
                r.raise_for_status()
                result = r.json()
                if result.get('code') != 1:
                    print(f"\n❌ Lỗi từ API: {result.get('msg')}")
                    break
                data_obj = result.get('data', {})
                page_list = data_obj.get('records') or data_obj.get('list') or []
                break
            except Exception as e:
                if attempt == max_retries:
                    print(f"\n❌ Lỗi kết nối trang {current_page}: {e}")
                    break
                time.sleep(attempt * 2)
                
        if page_list is None or not page_list:
            print("hết data.")
            break
            
        all_data.extend(page_list)
        print(f"✅ {len(page_list)} dòng")
        if len(page_list) < 1000:
            break
        current_page += 1
        time.sleep(0.3)
        
    print(f"   ➔ Hoàn tất Shuttle: {len(all_data)} dòng.")
    return pd.DataFrame(all_data)

def pull_linehaul(token):
    print("\n🚚 [2/4] Đang tải dữ liệu Liên tỉnh Linehaul từ J&T...")
    headers, payload = load_json_config(LINEHAUL_HEADERS_FILE, LINEHAUL_PAYLOAD_FILE)
    headers = set_token(headers, token)
    
    url = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
    
    payload['startTime'] = START_TIME
    payload['endTime'] = END_TIME
    payload['size'] = 200
    
    params = {
        "sqlCode": "transport_consolidated_report",
        "dcr_key": "57b048fb-bc8c-4d24-982b-a750b7ce8693"
    }
    
    all_data = []
    current_page = 1
    
    while True:
        print(f"   Trang {current_page}...", end=' ', flush=True)
        payload['current'] = current_page
        
        page_list = None
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
                if r.status_code in [401, 405] or r.json().get('code') in [401, 405]:
                    headers, new_token = handle_401(headers)
                    headers = set_token(headers, new_token)
                    r = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
                r.raise_for_status()
                result = r.json()
                if result.get('code') != 1:
                    print(f"\n❌ Lỗi từ API: {result.get('msg')}")
                    break
                data_obj = result.get('data', {})
                page_list = data_obj.get('records') or data_obj.get('list') or []
                break
            except Exception as e:
                if attempt == max_retries:
                    print(f"\n❌ Lỗi kết nối trang {current_page}: {e}")
                    break
                time.sleep(attempt * 2)
                
        if page_list is None or not page_list:
            print("hết data.")
            break
            
        all_data.extend(page_list)
        print(f"✅ {len(page_list)} dòng")
        if len(page_list) < 1000:
            break
        current_page += 1
        time.sleep(0.3)
        
    print(f"   ➔ Hoàn tất Linehaul: {len(all_data)} dòng.")
    return pd.DataFrame(all_data)

def load_stations():
    csv_path = os.path.join(BASE_DIR, "stations_master.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join(BASE_DIR, "config", "stations_master.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Không tìm thấy file bưu cục tại: {csv_path}")
        
    df_stations = pd.read_csv(csv_path)
    hcm_stations = df_stations[df_stations['master_area'].str.contains('HCM|SE', na=False, case=False)].copy()
    station_names = hcm_stations['station_name'].dropna().unique().tolist()
    
    valid_csv_path = os.path.join(VALID_DIR, "valid.csv")
    d_sortcode = {}
    if os.path.exists(valid_csv_path):
        df_valid = pd.read_csv(valid_csv_path, dtype=str)
        df_valid.columns = [c.strip() for c in df_valid.columns]
        
        station_col = next((c for c in ('Bưu cục final', 'Bưu cục', 'station_name') if c in df_valid.columns), None)
        code_col = next((c for c in ('sortcode', 'station_code') if c in df_valid.columns), None)
        
        if station_col and code_col:
            for _, r in df_valid.iterrows():
                name_val = str(r[station_col]).strip().upper()
                code_val = str(r[code_col]).strip()
                if name_val and code_val and name_val.lower() not in ('nan', 'none') and code_val.lower() not in ('nan', 'none'):
                    d_sortcode[name_val] = code_val
                    
    stations = []
    for name in station_names:
        name_clean = name.strip().upper()
        code = d_sortcode.get(name_clean)
        if not code:
            for k, v in d_sortcode.items():
                if name_clean in k or k in name_clean:
                    code = v
                    break
        if code:
            stations.append({'name': name.strip(), 'code': code})
            
    print(f"   📂 Đã chuẩn bị {len(stations)} bưu cục để kéo dữ liệu Phát hàng.")
    return stations

def pull_giam_sat_phat_hang(token, stations):
    print("\n🚚 [3/4] Bỏ qua tải dữ liệu Phát hàng theo yêu cầu tối ưu của user...")
    return pd.DataFrame()

def pull_incoming_cargo(token):
    print("\n🚚 [4/4] Đang tải dữ liệu Giám sát hàng đến (Đã đến + Chưa đến)...")
    headers, payload = load_json_config(INCOMING_HEADERS_FILE, INCOMING_PAYLOAD_FILE)
    headers['authToken'] = token
    headers['Authtoken'] = token
    
    url = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
    params = {
        'sqlCode': 'realtime_sca_arr_mon_dtl',
        'dcr_key': '57b048fb-bc8c-424d-982b-a750b7ce8693'
    }
    
    payload['beginDate'] = START_TIME
    payload['endDate'] = END_TIME
    payload['size'] = 200
    
    all_data = []
    
    # Chỉ kéo trạng thái sen (Chưa đến) theo yêu cầu của user
    for scan_type in ["sen"]:
        print(f"   🔄 Kéo trạng thái: Chưa đến (sen)...")
        current_page = 1
        
        while True:
            print(f"      Trang {current_page}...", end=' ', flush=True)
            payload['current'] = current_page
            payload['scanType'] = scan_type
            if scan_type == 'sen':
                payload['tmEmp'] = 'sen'
            else:
                payload.pop('tmEmp', None)
                
            page_list = None
            max_retries = 5
            for attempt in range(1, max_retries + 1):
                try:
                    r = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
                    if r.status_code in [401, 405] or r.json().get('code') in [401, 405]:
                        headers, new_token = handle_401(headers)
                        headers['authToken'] = new_token
                        headers['Authtoken'] = new_token
                        r = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
                    r.raise_for_status()
                    result = r.json()
                    if result.get('code') != 1:
                        print(f"\n❌ Lỗi từ API: {result.get('msg')}")
                        break
                    data_obj = result.get('data', {})
                    page_list = (
                        data_obj.get('records') or data_obj.get('list') or
                        data_obj.get('rows') or (data_obj if isinstance(data_obj, list) else [])
                    )
                    break
                except Exception as e:
                    if attempt == max_retries:
                        print(f"\n❌ Lỗi kết nối trang {current_page}: {e}")
                        break
                    time.sleep(attempt * 2)
                    
            if page_list is None or not page_list:
                print("hết data.")
                break
                
            all_data.extend(page_list)
            print(f"✅ {len(page_list)} dòng")
            if len(page_list) < 1000:
                break
            current_page += 1
            time.sleep(0.3)
            
    df = pd.DataFrame(all_data)
    print(f"   ➔ Hoàn tất Giám sát hàng đến: {len(df)} dòng.")
    return df

# ============================================================
# TIẾN TRÌNH CHÍNH (PIPELINE)
# ============================================================

def main():
    # 1. Khởi tạo Token chung
    token = get_valid_token()
    if not token:
        print("❌ Không lấy được token, dừng chương trình.")
        return
    
    # 2. Tải tất cả các nguồn dữ liệu J&T
    df_st = pull_shuttle(token)
    df_lh = pull_linehaul(token)
    
    try:
        stations = load_stations()
        df_ph = pull_giam_sat_phat_hang(token, stations)
    except Exception as e:
        print(f"⚠️ Không thể tải dữ liệu Giám sát phát hàng: {e}")
        df_ph = pd.DataFrame()
        
    df_inc = pull_incoming_cargo(token)
    
    if df_inc.empty:
        print("⚠️ Không có dữ liệu Giám sát hàng đến nào để xử lý.")
        return

    if 'scantime' not in df_inc.columns:
        df_inc['scantime'] = None

    # 3. Lập chỉ mục thời gian hành trình từ Shuttle và Linehaul
    print("\n🗂️ Đang lập chỉ mục thời gian từ Shuttle...")
    time_map = {}
    if not df_st.empty:
        for _, row in df_st.iterrows():
            tc = str(row.get('shipmentNo') or '').strip().upper()
            if tc:
                time_map[tc] = {
                    'gio_bat_dau_xep': str(row.get('loadStartTime') or '').strip(),
                    'gio_di_ke_hoach': str(row.get('plannedDepartureTime') or '').strip(),
                    'gio_den_ke_hoach': str(row.get('plannedArrivalTime') or '').strip(),
                    'gio_di_thuc_te': str(row.get('actualDepartureTime') or '').strip(),
                    'gio_den_thuc_te': str(row.get('actualArrivalTime') or '').strip(),
                    'source': 'Shuttle'
                }

    print("🗂️ Đang lập chỉ mục thời gian từ Linehaul...")
    if not df_lh.empty:
        for _, row in df_lh.iterrows():
            tc = str(row.get('shipmentNo') or '').strip().upper()
            if tc:
                # Ưu tiên hoặc đè lên
                time_map[tc] = {
                    'gio_bat_dau_xep': str(row.get('loadingScanStartTime') or '').strip(),
                    'gio_di_ke_hoach': str(row.get('plannedDepartureTime') or '').strip(),
                    'gio_den_ke_hoach': str(row.get('plannedArrivalTime') or '').strip(),
                    'gio_di_thuc_te': str(row.get('actualDepartureTime') or '').strip(),
                    'gio_den_thuc_te': str(row.get('actualArrivalTime') or '').strip(),
                    'source': 'Linehaul'
                }

    # 4. Khớp dữ liệu vào Giám sát hàng đến
    print("\n🔗 Đang tiến hành khớp mã chuyến (transfercode)...")
    col_xep = []
    col_di_kh = []
    col_den_kh = []
    col_di_tt = []
    col_den_tt = []
    col_source = []
    
    matched_st = 0
    matched_lh = 0
    unmatched = 0

    for _, row in df_inc.iterrows():
        tc = str(row.get('transfercode') or '').strip().upper()
        if tc in time_map:
            info = time_map[tc]
            col_xep.append(info['gio_bat_dau_xep'])
            col_di_kh.append(info['gio_di_ke_hoach'])
            col_den_kh.append(info['gio_den_ke_hoach'])
            col_di_tt.append(info['gio_di_thuc_te'])
            col_den_tt.append(info['gio_den_thuc_te'])
            col_source.append(info['source'])
            
            if info['source'] == 'Shuttle':
                matched_st += 1
            else:
                matched_lh += 1
        else:
            col_xep.append('')
            col_di_kh.append('')
            col_den_kh.append('')
            col_di_tt.append('')
            col_den_tt.append('')
            col_source.append('None')
            unmatched += 1

    df_inc['gio_bat_dau_xep'] = col_xep
    df_inc['gio_di_ke_hoach'] = col_di_kh
    df_inc['gio_den_ke_hoach'] = col_den_kh
    df_inc['gio_di_thuc_te'] = col_di_tt
    df_inc['gio_den_thuc_te'] = col_den_tt
    df_inc['nguon_anh_xa'] = col_source

    # 5. Tính toán ETA Incoming từ file etatrucking.csv
    print("⏳ Đang nạp định mức từ etatrucking.csv...")
    eta_dict = {}
    eta_file = os.path.join(VALID_DIR, "etatrucking.csv")
    if os.path.exists(eta_file):
        try:
            df_eta = pd.read_csv(eta_file, dtype=str)
            for _, row_eta in df_eta.iterrows():
                st = str(row_eta.get('station') or '').strip().upper()
                val = row_eta.get('ETA')
                if st and val is not None:
                    try:
                        eta_dict[st] = float(val)
                    except ValueError:
                        pass
            print(f"   ✅ Đã nạp {len(eta_dict)} định mức ETA.")
        except Exception as e:
            print(f"   ⚠️ Lỗi đọc etatrucking.csv: {e}")
    else:
        print(f"   ❌ Không tìm thấy file định mức ETA: {eta_file}")

    print("⏳ Đang tính toán cột 'ETA Incoming'...")
    col_eta_incoming = []
    for _, row in df_inc.iterrows():
        st = str(row.get('last_dept_name') or '').strip().upper()
        gio_di_tt = str(row.get('gio_di_thuc_te') or '').strip()
        
        eta_hours = eta_dict.get(st)
        if eta_hours is not None and gio_di_tt and gio_di_tt.lower() != 'nan' and gio_di_tt.lower() != '':
            try:
                dt_dep = datetime.strptime(gio_di_tt, '%Y-%m-%d %H:%M:%S')
                dt_eta = dt_dep + timedelta(hours=eta_hours)
                col_eta_incoming.append(dt_eta.strftime('%Y-%m-%d %H:%M:%S'))
            except Exception:
                col_eta_incoming.append('')
        else:
            col_eta_incoming.append('')
            
    df_inc['ETA Incoming'] = col_eta_incoming

    # 6. Kết hợp (Merge) với dữ liệu Phát hàng (được tối ưu hóa chạy bất kể df_ph rỗng)
    if df_ph.empty:
        df_ph = pd.DataFrame(columns=['billcode', 'scantime', 'package_charge_weight', 'scansitename'])
        
    print("\n🔗 Xử lý dữ liệu Giám sát hàng đến...")
    try:
        # A. Chuẩn bị bảng phát hàng sạch để merge (Giữ scansitename để bổ sung khi thiếu)
        df_ph_clean = df_ph[['billcode', 'scantime', 'package_charge_weight', 'scansitename']].copy()
        df_ph_clean.rename(columns={
            'scantime': 'arrival_time',
            'package_charge_weight': 'ph_weight',
            'scansitename': 'last_dept_name_ph'
        }, inplace=True)
        
        # Chuẩn bị các khóa để merge
        df_inc['billcode_clean'] = df_inc['billcode'].astype(str).str.strip().str.upper()
        df_ph_clean['billcode_clean'] = df_ph_clean['billcode'].astype(str).str.strip().str.upper()
        
        # B. Tính Ngày vận hành cho Phát hàng (Cycle 6h-6h)
        dt_ph_arr = pd.to_datetime(df_ph_clean['arrival_time'], errors='coerce')
        df_ph_clean['Ngày vận hành'] = (dt_ph_arr - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
        
        # Khử trùng lặp trong phát hàng theo billcode_clean & Ngày vận hành (giữ quét mới nhất trong ngày)
        df_ph_clean['sort_time_ph'] = dt_ph_arr
        df_ph_clean.sort_values(by='sort_time_ph', ascending=True, inplace=True)
        df_ph_clean.drop_duplicates(subset=['billcode_clean', 'Ngày vận hành'], keep='last', inplace=True)
        df_ph_clean.drop(columns=['sort_time_ph'], errors='ignore', inplace=True)
        
        # C. Tính Ngày vận hành cho Giám sát hàng đến (Cycle 6h-6h)
        dt_eta = pd.to_datetime(df_inc['ETA Incoming'], errors='coerce')
        
        scan_series = df_inc.get('scantime')
        if scan_series is None or scan_series.isna().all():
            scan_series = df_inc.get('gio_bat_dau_xep')
        if scan_series is None or scan_series.isna().all():
            scan_series = df_inc.get('gio_di_thuc_te')
            
        dt_scan = pd.to_datetime(scan_series, errors='coerce')
        base_time_inc = dt_eta.fillna(dt_scan)
        df_inc['Ngày vận hành'] = (base_time_inc - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
        
        # Merge Full Outer dựa trên cả billcode_clean & Ngày vận hành
        df_merged = pd.merge(
            df_inc,
            df_ph_clean,
            on=['billcode_clean', 'Ngày vận hành'],
            how='outer',
            suffixes=('', '_ph')
        )
        
        # Điền các cột cho những đơn chỉ có ở phát hàng
        only_ph_mask = df_merged['billcode'].isna()
        
        # ✂️ Chỉ giữ lại các đơn từ Phát hàng NẾU có Scantime (gio_bat_dau_xep)
        # Các đơn không có scantime = không xác định được giờ quét → bỏ ra khỏi dataset
        if 'gio_bat_dau_xep' in df_merged.columns:
            has_scantime = df_merged['gio_bat_dau_xep'].notna() & (df_merged['gio_bat_dau_xep'].astype(str).str.strip() != '') & (df_merged['gio_bat_dau_xep'].astype(str).str.strip().str.lower() != 'nan')
            only_ph_mask = only_ph_mask & has_scantime
            print(f"   ✂️ Lọc Phát hàng: chỉ giữ {only_ph_mask.sum()} dòng có Scantime (bỏ {(df_merged['billcode'].isna() & ~has_scantime).sum()} dòng thiếu scantime).")
        
        df_merged.loc[only_ph_mask, 'billcode'] = df_merged.loc[only_ph_mask, 'billcode_clean']
        df_merged.loc[only_ph_mask, 'package_charge_weight'] = df_merged.loc[only_ph_mask, 'ph_weight']
        df_merged.loc[only_ph_mask, 'scansitename'] = 'HCM HUB'
        df_merged.loc[only_ph_mask, 'ngay_tai_file'] = now.strftime('%Y-%m-%d %H:%M:%S')
        df_merged.loc[only_ph_mask, 'last_dept_name'] = df_merged.loc[only_ph_mask, 'last_dept_name_ph']
        
        # Loại bỏ các đơn từ Phát hàng không có scantime (billcode vẫn còn là NaN sau bộ lọc)
        df_merged = df_merged[df_merged['billcode'].notna()]
        
        df_inc = df_merged
        
        # --- CUSTOM DEDUPLICATION LOGIC ---
        print("\n⚙️ Đang thực hiện loại bỏ trùng lặp dựa trên mã vận đơn + Ngày vận hành (Chu kỳ 6h-6h)...")
        
        # Chuyển đổi lại các cột thời gian sang datetime để tính toán lại base_time hoàn chỉnh sau merge
        dt_eta_new = pd.to_datetime(df_inc['ETA Incoming'], errors='coerce')
        dt_arr_new = pd.to_datetime(df_inc['arrival_time'], errors='coerce')
        
        scan_series_new = df_inc.get('scantime')
        if scan_series_new is None or scan_series_new.isna().all():
            scan_series_new = df_inc.get('gio_bat_dau_xep')
        if scan_series_new is None or scan_series_new.isna().all():
            scan_series_new = df_inc.get('gio_di_thuc_te')
            
        dt_scan_new = pd.to_datetime(scan_series_new, errors='coerce')
        
        # Thời gian tham chiếu theo thứ tự ưu tiên: ETA Incoming -> arrival_time -> scantime
        base_time_new = dt_eta_new.fillna(dt_arr_new).fillna(dt_scan_new)
        
        # Tính lại Ngày vận hành chuẩn xác
        df_inc['Ngày vận hành'] = (base_time_new - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
        
        # Tạo khóa ghép: billcode + Ngày vận hành
        df_inc['bill_date_key'] = df_inc['billcode'].astype(str).str.strip().str.upper() + '|' + df_inc['Ngày vận hành'].fillna('')
        
        # Sắp xếp theo base_time_new tăng dần để khi drop_duplicates keep='last' sẽ giữ lại quét mới nhất
        df_inc['sort_time_temp'] = base_time_new
        df_inc.sort_values(by='sort_time_temp', ascending=True, inplace=True)
        
        # Loại bỏ các dòng trùng lặp cùng khóa bill_date_key
        df_inc.drop_duplicates(subset=['bill_date_key'], keep='last', inplace=True)
        
        # Xóa các cột phụ dùng để de-dup và merge (Giữ lại cột Ngày vận hành)
        df_inc.drop(columns=['sort_time_temp', 'bill_date_key', 'billcode_clean', 'billcode_ph', 'ph_weight', 'last_dept_name_ph'], errors='ignore', inplace=True)
        # --- END CUSTOM DEDUPLICATION LOGIC ---
        
        print(f"   ✅ Đã xử lý xong dữ liệu Giám sát hàng đến!")
    except Exception as e:
        print(f"   ⚠️ Lỗi khi xử lý dữ liệu Giám sát hàng đến: {e}")
        import traceback
        traceback.print_exc()

    # Sắp xếp thời gian xuất phát thực tế mới nhất lên đầu
    if 'gio_di_thuc_te' in df_inc.columns:
        df_inc = df_inc.reset_index(drop=True)
        temp_date = pd.to_datetime(df_inc['gio_di_thuc_te'], errors='coerce')
        df_inc = df_inc.iloc[temp_date.sort_values(ascending=False, na_position='last').index]
        df_inc = df_inc.reset_index(drop=True)

    # Bảo đảm cột arrival_time luôn tồn tại để tránh KeyError khi sync
    if 'arrival_time' not in df_inc.columns:
        df_inc['arrival_time'] = None

    # 7. Xuất file kết quả duy nhất
    now_save = datetime.now()
    output_filename = f"BaoCao_GiamSatHangDen_ChiTiet_Enriched_{now_save.strftime('%Y%m%d_%H%M%S')}.csv"
    output_file = os.path.join(INCOMING_DIR, output_filename)
    
    try:
        df_inc.to_csv(output_file, index=False, encoding='utf-8-sig')
    except PermissionError:
        output_filename = f"BaoCao_GiamSatHangDen_ChiTiet_Enriched_{now_save.strftime('%Y%m%d_%H%M%S')}_fallback.csv"
        output_file = os.path.join(INCOMING_DIR, output_filename)
        print(f"\n⚠️ Cảnh báo: Tệp gốc bị khóa (do Excel đang mở?), tự động lưu sang tệp: {output_filename}")
        df_inc.to_csv(output_file, index=False, encoding='utf-8-sig')

    supplemented = 0
    print("\n=======================================================")
    print("🎉 HOÀN THÀNH PIPELINE XỬ LÝ!")
    print("=======================================================")
    print(f"📂 File kết quả duy nhất: {output_file}")
    print(f"📊 Tổng số dòng cuối cùng: {len(df_inc)}")
    print(f"   ↳ Khớp với Shuttle:     {matched_st} dòng")
    print(f"   ↳ Khớp với Linehaul:    {matched_lh} dòng")
    print(f"   ↳ Không khớp (Thiếu):   {unmatched} dòng")
    print(f"   ↳ Bổ sung từ Phát hàng: {supplemented} dòng")
    print("=======================================================")

if __name__ == "__main__":
    main()
