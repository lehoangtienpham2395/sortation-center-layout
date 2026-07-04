import os
import json
import time
import math
import hashlib
import threading
import sys
import io
import requests
from datetime import datetime, timedelta
import pandas as pd
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Thiết lập ghi log unicode trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# ============================================================
# CONFIG
# ============================================================
BASE_DIR   = r"C:\Users\lehoa\OneDrive\Desktop\testing"
OUTPUT_DIR = r"C:\Users\lehoa\OneDrive\Desktop\testing"
ACCOUNT    = "660021"
PASSWORD   = "Tien@giang2395"
COUNTRY_ID = "1"

# Google Sheets – dùng để đọc sheet Inbound để mapping billNo
SPREADSHEET_ID = "1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI"

POOL_SIZE        = 32
PAGE_WORKERS     = 8
REQUEST_TIMEOUT  = 60
MAX_RETRIES      = 5
BACKOFF_BASE     = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

URL_SCAN     = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
URL_SELECT   = 'https://gw.jtcargo.com.vn/basicdata/network/select'
LOGIN_URL    = "https://gw.jtcargo.com.vn/basicdata/login"

LOGIN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://jfs.jtcargo.com.vn",
    "Referer": "https://jfs.jtcargo.com.vn/",
    "lang": "VN",
    "langtype": "VN",
    "routeName": "checkToken",
}

def md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def build_session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE, max_retries=0)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s

class TokenManager:
    def __init__(self, session, account, password, country_id='1'):
        self.session    = session
        self.account    = account
        self.password   = password
        self.country_id = country_id
        self._token     = None
        self._lock      = threading.Lock()

    def _login(self) -> str:
        payload = {
            'account':      self.account,
            'password':     md5(self.password),
            'captchaToken': '',
            'countryId':    self.country_id,
        }
        for attempt in range(1, 4):
            try:
                r = self.session.post(LOGIN_URL, headers=LOGIN_HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                result = r.json()
                if result.get('code') == 1 or result.get('succ'):
                    data  = result.get('data', {})
                    token = data.get('token') or data.get('authToken') or (data if isinstance(data, str) else None)
                    if token:
                        return token
                print(f"   [Thử lại {attempt}/3] Đăng nhập không thành công: {result.get('msg', result)}")
            except Exception as e:
                print(f"   [Thử lại {attempt}/3] Lỗi mạng khi đăng nhập: {e}")
            time.sleep(2 * attempt)
        raise RuntimeError("Đăng nhập thất bại hoàn toàn sau 3 lần thử.")

    def get_token(self) -> str:
        with self._lock:
            if self._token is None:
                print('   🔄 Đang login JFS...')
                self._token = self._login()
                print(f'   ✅ Đăng nhập thành công | token: {self._token[:12]}...')
            return self._token

    def refresh(self, stale_token: str) -> str:
        with self._lock:
            if self._token is None or self._token == stale_token:
                print('   ⚠️ Token hết hạn → đang login lại...')
                self._token = self._login()
                print(f'   ✅ Login lại thành công | token: {self._token[:12]}...')
            return self._token

def auth_post(session, url, token_mgr, base_headers, params=None, json_body=None, label=''):
    last_exc  = None
    refreshed = False
    attempt   = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        token   = token_mgr.get_token()
        headers = dict(base_headers)
        headers['Authtoken'] = token
        headers['authToken'] = token
        try:
            r = session.post(url, params=params, headers=headers, json=json_body, timeout=REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            wait = BACKOFF_BASE * attempt
            print(f'   ⏱️ {label} lỗi mạng: {type(e).__name__}, chờ {wait}s...')
            time.sleep(wait)
            continue

        if r.status_code == 401 and not refreshed:
            token_mgr.refresh(token)
            refreshed = True
            attempt  -= 1
            continue

        if r.status_code in RETRYABLE_STATUS:
            last_exc = requests.exceptions.HTTPError(f'{r.status_code} {url}')
            time.sleep(BACKOFF_BASE * attempt)
            continue

        r.raise_for_status()
        return r

    raise last_exc if last_exc else RuntimeError(f'{label}: thất bại sau {MAX_RETRIES} lần thử')

def auth_get(session, url, token_mgr, base_headers, params=None, label=''):
    last_exc  = None
    refreshed = False
    attempt   = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        token   = token_mgr.get_token()
        headers = dict(base_headers)
        headers['Authtoken'] = token
        headers['authToken'] = token
        try:
            r = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            wait = BACKOFF_BASE * attempt
            print(f'   ⏱️ {label} lỗi mạng: {type(e).__name__}, chờ {wait}s...')
            time.sleep(wait)
            continue

        if r.status_code == 401 and not refreshed:
            token_mgr.refresh(token)
            refreshed = True
            attempt  -= 1
            continue

        if r.status_code in RETRYABLE_STATUS:
            last_exc = requests.exceptions.HTTPError(f'{r.status_code} {url}')
            time.sleep(BACKOFF_BASE * attempt)
            continue

        r.raise_for_status()
        return r

    raise last_exc if last_exc else RuntimeError(f'{label}: thất bại sau {MAX_RETRIES} lần thử')

def get_station_info(session, token_mgr, headers, station_name):
    """Tìm mã code, ID và TypeID của bưu cục dựa trên tên bưu cục tiếng Việt (rút gọn)"""
    # Rút gọn tên bưu cục (Bỏ CT, AG, SG ở đầu để tìm kiếm chính xác trên JFS)
    parts = station_name.strip().split(' ', 1)
    search_name = parts[1] if len(parts) > 1 else station_name
    
    params = {
        "dcr_key": "57b048fb-bc8c-4d24-982b-a750b7ce8693",
        "name": search_name,
        "networkId": "11888",
        "queryLevel": "3",
        "current": 1,
        "size": 20
    }
    try:
        r = auth_get(session, URL_SELECT, token_mgr, headers, params=params, label=f'Select {search_name}')
        res_json = r.json()
        if res_json.get('succ') or res_json.get('code') == 1:
            records = res_json.get('data', {}).get('records', [])
            if records:
                # So khớp chính xác hoặc khớp tương đối
                for rec in records:
                    rec_name = rec.get('name', '').upper()
                    if station_name.upper() in rec_name or search_name.upper() in rec_name:
                        return {
                            "code": rec.get('code') or rec.get('networkCode'),
                            "id": rec.get('id'),
                            "name": rec.get('name'),
                            "typeId": rec.get('typeId') or rec.get('networkTypeId')
                        }
    except Exception as e:
        print(f"      ⚠️ Lỗi lấy thông tin trạm {station_name}: {e}")
    return None


# ============================================================
# HÀM LẤY TẬP HỢP BILLNO ĐÃ VỀ HUB TỪ SHEET INBOUND
# (Google Sheets công khai – đọc qua gviz CSV)
# ============================================================
def fetch_inbound_billnos() -> set:
    """
    Đọc sheet Inbound từ Google Sheets, trả về tập hợp billNo đã ghi nhận
    (tức là đã về Hub). Dashboard sử dụng cột 'billNo' trong sheet Inbound.
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
        f"/gviz/tq?tqx=out:csv&sheet=Inbound"
    )
    try:
        print("   📡 Đang đọc sheet Inbound từ Google Sheets để mapping billNo...")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        from io import StringIO
        df_ib = pd.read_csv(StringIO(r.text))
        # Chuẩn hóa tên cột
        df_ib.columns = [c.strip().strip('"') for c in df_ib.columns]
        if 'billNo' in df_ib.columns:
            billnos = set(df_ib['billNo'].dropna().astype(str).str.strip().tolist())
            print(f"   ✅ Đã lấy {len(billnos):,} mã billNo từ sheet Inbound.")
            return billnos
        else:
            print(f"   ⚠️ Không tìm thấy cột 'billNo' trong sheet Inbound. Các cột hiện có: {list(df_ib.columns)}")
            return set()
    except Exception as e:
        print(f"   ❌ Lỗi đọc sheet Inbound: {e}")
        return set()


# ============================================================
# HÀM ĐỌC DỮ LIỆU ARRIVAL CŨ (UPSERT TÍCH LŨY)
# ============================================================
def load_existing_arrival(out_path: str) -> pd.DataFrame:
    """
    Đọc sheet Arrival hiện có từ file Excel nếu tồn tại.
    Trả về DataFrame rỗng nếu file chưa tồn tại hoặc sheet chưa có.
    """
    if not os.path.exists(out_path):
        return pd.DataFrame()
    try:
        xl = pd.ExcelFile(out_path, engine='openpyxl')
        if 'Arrival' in xl.sheet_names:
            df_old = pd.read_excel(xl, sheet_name='Arrival')
            print(f"   📂 Đọc được {len(df_old):,} dòng Arrival cũ từ file Excel.")
            return df_old
    except Exception as e:
        print(f"   ⚠️ Không thể đọc sheet Arrival cũ: {e}")
    return pd.DataFrame()


def upsert_arrival(df_old: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    """
    Upsert theo key (Ngày vận hành, Pickup_station, Scan Hour):
    - Dữ liệu cùng key → cập nhật bằng dữ liệu mới
    - Dữ liệu ngày cũ không có trong đợt chạy này → giữ nguyên
    """
    key_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour']

    if df_old.empty:
        return df_new

    # Đảm bảo key cols đều là string để join đúng
    for col in key_cols:
        if col in df_old.columns:
            df_old[col] = df_old[col].astype(str).str.strip()
        if col in df_new.columns:
            df_new[col] = df_new[col].astype(str).str.strip()

    # Tạo composite key
    df_old['_key'] = df_old[key_cols].agg('|'.join, axis=1)
    df_new['_key'] = df_new[key_cols].agg('|'.join, axis=1)

    new_keys = set(df_new['_key'])
    # Giữ lại các dòng cũ mà key không bị update
    df_keep = df_old[~df_old['_key'].isin(new_keys)].drop(columns=['_key'])
    df_new  = df_new.drop(columns=['_key'])

    result = pd.concat([df_keep, df_new], ignore_index=True)
    result = result.sort_values(by=['Ngày vận hành', 'Pickup_station', 'Scan Hour'],
                                ascending=[False, True, True])
    return result


def main():
    print("==========================================================")
    print("ETL PIPELINE: GIÁM SÁT PHÁT HÀNG (REALTIME - MULTI STATIONS)")
    print("==========================================================")
    
    session = build_session()
    token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=utf-8",
        "Origin": "https://jfs.jtcargo.com.vn",
        "Referer": "https://jfs.jtcargo.com.vn/",
        "Routename": "Bd-theme-1d2e14d9-6dcc-437e-afb2-0afc668d7d50|businessIndicatorIndex",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }

    # Đọc danh sách bưu cục từ stations_master.csv
    csv_path = os.path.join(BASE_DIR, "stations_master.csv")
    if not os.path.exists(csv_path):
        print(f"❌ Không tìm thấy file danh sách bưu cục tại: {csv_path}")
        return
        
    df_stations = pd.read_csv(csv_path)
    # Lấy các trạm thuộc HCM (cột master_area chứa HCM)
    hcm_stations = df_stations[df_stations['master_area'].str.contains('HCM', na=False, case=False)]
    station_names = hcm_stations['station_name'].dropna().unique().tolist()
    
    print(f"📂 Đọc thành công {len(station_names)} bưu cục từ stations_master.csv")
    
    # Thiết lập thời gian lọc (hôm nay)
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_time = f"{today_str} 00:00:00"
    end_time = f"{today_str} 23:59:59"
    print(f"📅 Khoảng thời gian lọc: {start_time} -> {end_time}")

    # ── Bước 1: Lấy billNo đã về Hub từ sheet Inbound ──────────────────────
    print("\n🔍 Bước 1: Lấy danh sách billNo đã về Hub từ Google Sheets...")
    inbound_billnos = fetch_inbound_billnos()

    # ── Bước 2: Tra cứu mã bưu cục từ JFS ─────────────────────────────────
    print("\n🔍 Bước 2: Đang tra cứu mã bưu cục (JFS Codes) từ hệ thống...")
    valid_stations_info = []
    
    # Giới hạn tìm kiếm song song để tăng tốc lấy mã trạm
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {executor.submit(get_station_info, session, token_mgr, headers, name): name for name in station_names}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                info = future.result()
                if info:
                    valid_stations_info.append(info)
            except Exception as e:
                print(f"   ⚠️ Lỗi tra cứu trạm {name}: {e}")

    print(f"✅ Đã tìm thấy mã JFS của {len(valid_stations_info)}/{len(station_names)} bưu cục.")

    # ── Bước 3: Tải dữ liệu phát hàng từ JFS ──────────────────────────────
    all_data = []
    lock = threading.Lock()
    
    params = {
        "sqlCode": "realtime_sca_sen_mon_dtl",
        "dcr_key": "57b048fb-bc8c-4d24-982b-a750b7ce8693"
    }

    def fetch_station_data(station):
        # Payload riêng cho từng bưu cục
        payload = {
            "beginDate": start_time,
            "endDate": end_time,
            "nextStationCode": "HCM004H",
            "nextStationCodeId": 11888,
            "nextStationCodeName": "HCM HUB",
            "nextStationCodeTypeId": 335,
            "countryId": "1",
            "size": 1000,
            "sqlCode": "realtime_sca_sen_mon_dtl",
            "wayType": "1",
            # Thông tin bưu cục phát đi
            "scanSiteCode": station["code"],
            "scanSiteCodeId": station["id"],
            "scanSiteCodeName": station["name"],
            "scanSiteCodeTypeId": station["typeId"]
        }
        
        # Gọi lấy tổng số dòng trước
        station_data = []
        try:
            count_payload = {**payload, 'paginationSearchType': 'count', 'size': 1, 'current': 1}
            r = auth_post(session, URL_SCAN, token_mgr, headers, params=params, json_body=count_payload, label=f'Count {station["name"]}')
            res_json = r.json()
            total = None
            if res_json.get('succ') or res_json.get('code') == 1:
                data_node = res_json.get('data')
                if isinstance(data_node, dict):
                    total = data_node.get('total', None)
            
            if total is None or total == 0:
                return
                
            # Tải dữ liệu thực tế
            n_pages = math.ceil(total / 1000)
            print(f"   📥 Bưu cục [{station['name']}]: Có {total} dòng, đang tải {n_pages} trang...")
            
            for p in range(1, n_pages + 1):
                list_payload = {**payload, 'paginationSearchType': 'list', 'current': p}
                r_list = auth_post(session, URL_SCAN, token_mgr, headers, params=params, json_body=list_payload, label=f'{station["name"]} p{p}')
                res_list_json = r_list.json()
                
                data_node_list = res_list_json.get('data')
                records = []
                if isinstance(data_node_list, dict):
                    records = data_node_list.get('records', [])
                elif isinstance(data_node_list, list):
                    records = data_node_list
                    
                if records:
                    station_data.extend(records)
                    
            if station_data:
                with lock:
                    all_data.extend(station_data)
                print(f"   ✅ Bưu cục [{station['name']}]: Đã tải thành công {len(station_data)} dòng.")
                
        except Exception as e:
            print(f"   ❌ Lỗi tải dữ liệu cho bưu cục {station['name']}: {e}")

    # Chạy kéo dữ liệu song song các bưu cục
    print("\n🚀 Bước 3: Bắt đầu tải dữ liệu phát hàng song song từ các bưu cục...")
    if valid_stations_info:
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(fetch_station_data, valid_stations_info)

    if not all_data:
        print("⚠️ Không tìm thấy dữ liệu phát hàng nào gửi về HCM HUB từ tất cả bưu cục trong ngày.")
        return

    # Ghi 1 bản ghi mẫu để kiểm tra các trường dữ liệu thô
    try:
        with open(os.path.join(OUTPUT_DIR, "sample_record.json"), "w", encoding="utf-8") as f:
            json.dump(all_data[0], f, ensure_ascii=False, indent=4)
        print("💾 Đã lưu 1 bản ghi thô vào file sample_record.json để đối chiếu trường ẩn.")
    except Exception as e:
        print(f"⚠️ Không thể lưu bản ghi mẫu: {e}")

    df = pd.DataFrame(all_data)
    
    # ── Bước 4: Tính Ngày vận hành (Cycle 6h-6h) ───────────────────────────
    try:
        df['scantime_dt'] = pd.to_datetime(df['scantime'], errors='coerce')
        df['Ngày vận hành'] = (df['scantime_dt'] - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
        df['Scan Hour'] = df['scantime_dt'].dt.hour  # Giờ thực tế (0-23) cho biểu đồ
        df = df.drop(columns=['scantime_dt'])
    except Exception as e:
        print(f"⚠️ Không thể tính Ngày vận hành: {e}")

    # Đổi tên cột scansitename → Pickup_station
    if 'scansitename' in df.columns:
        df = df.rename(columns={'scansitename': 'Pickup_station'})
        
    # Đưa cột quan trọng lên đầu bảng
    priority_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour']
    remaining_cols = [c for c in df.columns if c not in priority_cols]
    df = df[priority_cols + remaining_cols]

    # ── Bước 5: Mapping "Đã đến Hub" / "Chưa đến Hub" ──────────────────────
    print("\n🔗 Bước 5: Mapping billNo với dữ liệu Inbound...")
    if inbound_billnos:
        billcode_col = 'billcode'  # Tên cột từ JFS API
        if billcode_col in df.columns:
            df['Đã đến Hub'] = df[billcode_col].astype(str).str.strip().isin(inbound_billnos).astype(int)
            df['Chưa đến Hub'] = (1 - df['Đã đến Hub'])
            da_den = df['Đã đến Hub'].sum()
            chua_den = df['Chưa đến Hub'].sum()
            print(f"   ✅ Mapping hoàn thành: Đã đến Hub={da_den:,} | Chưa đến Hub={chua_den:,}")
        else:
            print(f"   ⚠️ Không tìm thấy cột '{billcode_col}' trong dữ liệu JFS. Bỏ qua mapping.")
            df['Đã đến Hub'] = 0
            df['Chưa đến Hub'] = 1
    else:
        print("   ⚠️ Không có dữ liệu Inbound để mapping. Tất cả đánh dấu là 'Chưa đến Hub'.")
        df['Đã đến Hub'] = 0
        df['Chưa đến Hub'] = 1

    out_path = os.path.join(OUTPUT_DIR, "danh_sach_HCM_HUB.xlsx")

    # ── Bước 6: Tạo bảng Pivot "Tổng hợp đơn gửi về" (giữ nguyên như cũ) ──
    df_pivot = pd.DataFrame()
    try:
        df['scantime_dt'] = pd.to_datetime(df['scantime'], errors='coerce')
        
        df_pivot = df.groupby(['Ngày vận hành', 'Pickup_station']).agg(
            Tổng_số_đơn=('billcode', 'size'),
            Last_time_dt=('scantime_dt', 'max')
        ).reset_index()
        
        df_pivot['Last time'] = df_pivot['Last_time_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_pivot = df_pivot.drop(columns=['Last_time_dt'])
        df_pivot = df_pivot.rename(columns={'Tổng_số_đơn': 'Tổng số đơn'})
        df_pivot = df_pivot.sort_values(by=['Ngày vận hành', 'Tổng số đơn'], ascending=[False, False])
        df = df.drop(columns=['scantime_dt'], errors='ignore')
        
        print(f"📊 Đã tạo bảng Pivot 'Tổng hợp đơn gửi về' thành công!")
    except Exception as e:
        print(f"⚠️ Lỗi tạo bảng Pivot Tổng hợp: {e}")

    # ── Bước 7: Tạo sheet Arrival (Pivot tích lũy theo ngày + trạm + giờ) ──
    print("\n📋 Bước 7: Tạo sheet Arrival (tích lũy theo ngày, trạm và giờ)...")
    df_arrival_new = pd.DataFrame()
    try:
        # Pivot mới: group by Ngày vận hành + Pickup_station + Scan Hour
        agg_dict = {
            'Tổng số đơn': ('billcode', 'size'),
        }
        if 'Đã đến Hub' in df.columns:
            agg_dict['Đã đến Hub']   = ('Đã đến Hub', 'sum')
            agg_dict['Chưa đến Hub'] = ('Chưa đến Hub', 'sum')

        # Cần scantime để lấy last time
        df['scantime_dt_arr'] = pd.to_datetime(df['scantime'], errors='coerce')
        agg_dict['Last_time_dt'] = ('scantime_dt_arr', 'max')

        df_arrival_new = df.groupby(['Ngày vận hành', 'Pickup_station', 'Scan Hour']).agg(
            **agg_dict
        ).reset_index()

        df_arrival_new['Last time'] = df_arrival_new['Last_time_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_arrival_new = df_arrival_new.drop(columns=['Last_time_dt'])
        df = df.drop(columns=['scantime_dt_arr'], errors='ignore')

        # Upsert với dữ liệu cũ để tích lũy lịch sử
        df_arrival_old = load_existing_arrival(out_path)
        df_arrival_final = upsert_arrival(df_arrival_old, df_arrival_new)

        print(f"   ✅ Sheet Arrival: {len(df_arrival_final):,} dòng (sau upsert). Ngày mới nhất: {df_arrival_new['Ngày vận hành'].max()}")
    except Exception as e:
        print(f"⚠️ Lỗi tạo sheet Arrival: {e}")
        df_arrival_final = pd.DataFrame()

    # ── Bước 8: Ghi file Excel với 3 sheets ───────────────────────────────
    print(f"\n💾 Bước 8: Ghi file Excel...")
    try:
        with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Chi tiết', index=False)
            if not df_pivot.empty:
                df_pivot.to_excel(writer, sheet_name='Tổng hợp đơn gửi về', index=False)
            if not df_arrival_final.empty:
                df_arrival_final.to_excel(writer, sheet_name='Arrival', index=False)
    except Exception as e:
        print(f"⚠️ Lỗi ghi file Excel: {e}")
        df.to_excel(out_path, index=False)

    print("==========================================================")
    print(f"🎉 HOÀN THÀNH: Đã gộp và lưu {len(all_data):,} dòng vào file:")
    print(f"   📄 Sheet 'Chi tiết'              : {len(df):,} dòng")
    print(f"   📊 Sheet 'Tổng hợp đơn gửi về'  : {len(df_pivot):,} dòng")
    if not df_arrival_final.empty:
        print(f"   🗂️  Sheet 'Arrival' (tích lũy)  : {len(df_arrival_final):,} dòng")
    print(f"👉 {out_path}")
    print("==========================================================")
    print()
    print("📌 HƯỚNG DẪN TIẾP THEO:")
    print("   1. Mở file Excel vừa tạo, copy toàn bộ dữ liệu từ sheet 'Arrival'")
    print(f"   2. Dán vào sheet 'Arrival' trong Google Sheets:")
    print(f"      https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    print("   3. Dashboard sẽ tự động đọc và cập nhật sau khi bấm 'Đồng bộ'")

if __name__ == '__main__':
    main()
