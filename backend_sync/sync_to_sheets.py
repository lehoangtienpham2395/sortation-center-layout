import os
import re
import json
import time
import math
import hashlib
import argparse
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from requests.adapters import HTTPAdapter

import sqlite3

# ============================================================
# CONFIG ĐĂNG NHẬP (Đọc từ GitHub Secrets / Environment Variables)
# ============================================================
ACCOUNT    = os.environ.get("SYSTEM_ACCOUNT", "").strip() or "660021"
PASSWORD   = os.environ.get("SYSTEM_PASSWORD", "").strip() or "Tien@giang2395"
COUNTRY_ID = "1"
LOGIN_URL  = "https://gw.jtcargo.com.vn/basicdata/login"

# Google Sheet ID
SHEET_ID = "1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI"

# ============================================================
# CONFIG ĐƯỜNG DẪN CỤC BỘ (Relative to Script Path)
# ============================================================
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR   = os.path.join(BASE_DIR, "output")
VALID_FILE   = os.path.join(BASE_DIR, "config", "valid.csv")
DB_FILE      = os.path.join(BASE_DIR, "db", "state.db")

# ============================================================
# ENDPOINTS (GIỮ NGUYÊN)
# ============================================================
URL_FORECAST       = 'https://gw.jtcargo.com.vn/networkmanagement/omsWaybill/shippingWaybillList'
URL_FORECAST_COUNT = 'https://gw.jtcargo.com.vn/networkmanagement/omsWaybill/shippingWaybillListCount'
URL_SCAN           = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
URL_DISPATCH       = 'https://gw.jtcargo.com.vn/customerplatform/omsOrderDispatch/page'

# New correct operating platform endpoints for Linehaul, Arrival & Departure
URL_LINEHAUL       = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryTraceSubForPage'
URL_UNLOADING      = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryOpsUnloadingSchedulForPage'
URL_LOADING        = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryOpsLoadingSchedulForPage'


# ============================================================
# TUNING
# ============================================================
SOURCE_WORKERS      = 5
PAGE_WORKERS        = 2
POOL_SIZE           = 32
REQUEST_TIMEOUT     = 60
MAX_RETRIES         = 5
BACKOFF_BASE        = 3
INTER_REQUEST_DELAY = 0

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

LOGIN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://jfs.jtcargo.com.vn",
    "Referer": "https://jfs.jtcargo.com.vn/",
    "lang": "VN",
    "langtype": "VN",
    "routeName": "checkToken",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}


# ================================================================
# AUTH
# ================================================================
def md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def build_session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE, max_retries=0)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s


class TokenManager:
    def __init__(self, session: requests.Session, account: str, password: str, country_id: str):
        self.session = session
        self.account = account
        self.password = password
        self.country_id = country_id
        self._token = None
        self._lock = threading.Lock()

    def _login(self) -> str:
        payload = {
            "account":      self.account,
            "password":     md5(self.password),
            "captchaToken": "",
            "countryId":    self.country_id,
        }
        r = self.session.post(LOGIN_URL, headers=LOGIN_HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        result = r.json()
        if result.get('code') == 1 or result.get('succ'):
            data = result.get('data', {})
            token = data.get('token') or data.get('authToken') or (data if isinstance(data, str) else None)
            if token:
                return token
            raise RuntimeError(f"Login OK nhưng không tìm thấy token. Response: {result}")
        raise RuntimeError(f"Login thất bại: {result.get('msg', result)}")

    def get_token(self) -> str:
        with self._lock:
            if self._token is None:
                print("   🔄 Đang login...")
                self._token = self._login()
                print(f"   ✅ Đăng nhập thành công | token: {self._token[:12]}...")
            return self._token

    def refresh(self, stale_token: str) -> str:
        with self._lock:
            if self._token is None or self._token == stale_token:
                print("   ⚠️  Token hết hạn (401) → đang login lại...")
                self._token = self._login()
                print(f"   ✅ Login lại thành công | token: {self._token[:12]}...")
            return self._token


def get_operating_date(dt_str):
    if not dt_str or str(dt_str).strip() in ('', 'nan', 'None'):
        return ""
    try:
        dt = pd.to_datetime(dt_str)
        if dt.hour < 6:
            return (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            return dt.strftime('%Y-%m-%d')
    except Exception:
        return ""


def init_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # ⚡ TỐI ƯU HÓA HIỆU NĂNG GHI/ĐỌC SQLITE CỰC ĐẠI
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = OFF")
    c.execute("PRAGMA cache_size = -64000")  # Cache RAM 64MB
    c.execute("PRAGMA temp_store = MEMORY")
    c.execute("PRAGMA count_changes = OFF")
    
    # Tạo bảng inventory thô để gom nhóm lưu trữ
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            waybillNo TEXT PRIMARY KEY,
            data_source TEXT,
            weight REAL,
            pickNetworkName TEXT,
            dispatch_plan TEXT,
            Pickup_time TEXT,
            pickup_label TEXT,
            Pickup_ontime TEXT,
            dispatchNetworkTime TEXT,
            next_station TEXT,
            Tuyến TEXT,
            Rank TEXT,
            inbound_network TEXT,
            inbound_scanDate TEXT,
            outbound_scanDate TEXT,
            dispatch_actual TEXT,
            status_order TEXT,
            time_ref TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Tạo index tối ưu hóa query filter & group by
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_time_ref ON inventory(time_ref)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON inventory(status_order)")
    
    # Auto dọn dẹp các record cũ hơn 7 ngày để tối ưu hóa dung lượng DB
    try:
        limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("DELETE FROM inventory WHERE datetime(last_updated) < datetime(?)", (limit_date,))
        conn.commit()
    except Exception as e_clean:
        print(f"   ⚠️ Lỗi dọn dẹp database: {e_clean}")
    
    conn.close()


def auth_post(session, url, token_mgr, base_headers, *,
              params=None, json_body=None, data=None,
              timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES, label=''):
    last_exc = None
    refreshed = False
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        token = token_mgr.get_token()
        if not token:
            raise RuntimeError(f"{label}: không lấy được token")
        headers = dict(base_headers)
        headers['authToken'] = token
        try:
            r = session.post(url, params=params, headers=headers,
                             json=json_body, data=data, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            time.sleep(BACKOFF_BASE * attempt)
            continue

        if r.status_code == 401 and not refreshed:
            token_mgr.refresh(token)
            refreshed = True
            attempt -= 1
            continue

        if r.status_code in RETRYABLE_STATUS:
            last_exc = requests.exceptions.HTTPError(f"{r.status_code} {url}")
            time.sleep(BACKOFF_BASE * attempt)
            continue

        r.raise_for_status()
        return r

    raise last_exc if last_exc else RuntimeError(f"{label}: thất bại sau {max_retries} lần thử")


def pull_pages_parallel(fetch_page, total, page_size, label, start_page=1):
    n_pages = math.ceil(total / page_size)
    pages = list(range(start_page, n_pages + 1))
    
    results = {}
    failed_pages = []

    def execute_fetch(p):
        try:
            return fetch_page(p)
        except Exception:
            return None

    print(f"   🚀 Đang tải {len(pages)} trang cho {label}...")
    
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        future_to_page = {ex.submit(execute_fetch, p): p for p in pages}
        for f in as_completed(future_to_page):
            p = future_to_page[f]
            res = f.result()
            if res is not None:
                results[p] = res
            else:
                failed_pages.append(p)

    if failed_pages:
        print(f"   ⚠️ Có {len(failed_pages)} trang lỗi, đang thử lại lần 2...")
        for p in failed_pages:
            time.sleep(1)
            res = execute_fetch(p)
            if res is not None:
                results[p] = res
            else:
                print(f"   ❌ Trang {p} vẫn lỗi sau khi thử lại.")
                results[p] = []

    out = []
    for p in pages:
        out.extend(results.get(p, []))
    return out


def pull_pages_sequential(fetch_page, page_size, label,
                          total=None, stop_short=True, start_page=1, seed=None):
    all_data = list(seed) if seed else []
    page = start_page
    while True:
        try:
            page_list = fetch_page(page)
        except Exception as e:
            print(f"   ❌ {label} trang {page}: {e}")
            break
        if not page_list:
            break
        all_data.extend(page_list)
        if isinstance(total, int) and len(all_data) >= total:
            break
        if stop_short and len(page_list) < page_size:
            break
        page += 1
        if INTER_REQUEST_DELAY:
            time.sleep(INTER_REQUEST_DELAY)
    return all_data



# ================================================================
# ARRIVAL PULLER (Giám sát phát hàng từ JFS – gom theo bưu cục)
# ================================================================
URL_ARRIVAL_SELECT  = 'https://gw.jtcargo.com.vn/basicdata/network/select'
URL_ARRIVAL_SCAN    = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
ARRIVAL_PARAMS      = {'sqlCode': 'realtime_sca_sen_mon_dtl', 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693'}


def pull_arrival_from_jfs(session, token_mgr, base_headers, date_start, date_end):
    """
    Kéo dữ liệu giám sát phát hàng gửi về HCM HUB từ tất cả bưu cục HCM/SE (Miền Nam).
    Sử dụng giải pháp Code-Only, bỏ qua API Select để tránh lỗi phân quyền/401 và tăng tốc độ.
    """
    # 1. Đọc danh sách bưu cục Miền Nam (HCM/SE) + BN HUB từ stations_master.csv ở thư mục Desktop
    station_names = []
    master_path = r"C:\Users\lehoa\OneDrive\Desktop\testing\stations_master.csv"
    if os.path.exists(master_path):
        try:
            df_m = pd.read_csv(master_path)
            # Lấy các trạm thuộc HCM và SE (Đông Nam) và bổ sung BN HUB
            df_filtered = df_m[
                df_m['master_area'].str.contains('HCM|SE', na=False, case=False) |
                df_m['station_name'].str.contains('BN HUB', na=False, case=False)
            ].copy()
            station_names = df_filtered['station_name'].dropna().unique().tolist()
            print(f"   📂 Load thành công {len(station_names)} bưu cục (bao gồm BN HUB) từ stations_master.csv.")
        except Exception as e_sm:
            print(f"   ⚠️ Lỗi đọc stations_master.csv: {e_sm}")
            
    if not station_names:
        print('   ⚠️ Arrival: không có bưu cục để kéo.')
        return []

    # 2. Đọc mapping sortcode từ valid.csv cục bộ
    d_sortcode = {}
    try:
        if os.path.exists(VALID_FILE):
            df_v = pd.read_csv(VALID_FILE, encoding='utf-8-sig', dtype=str)
            df_v.columns = df_v.columns.str.strip()
            # Ưu tiên cột 'Bưu cục' (cột 1) để BN HUB map đúng sortcode BNI001H gốc của nó
            name_col = 'Bưu cục' if 'Bưu cục' in df_v.columns else ('Bưu cục final' if 'Bưu cục final' in df_v.columns else None)
            if name_col and 'sortcode' in df_v.columns:
                df_filtered_v = df_v[[name_col, 'sortcode']].dropna()
                d_sortcode = {
                    str(row[name_col]).strip().upper(): str(row['sortcode']).strip()
                    for _, row in df_filtered_v.iterrows()
                    if str(row['sortcode']).strip() != '' and not any(x in str(row['sortcode']).lower() for x in ('offline', 'nan', 'none'))
                }
                print(f"   ✅ Đã nạp mapping sortcode từ valid.csv: {len(d_sortcode)} bưu cục.")
        else:
            print(f"   ⚠️ Không tìm thấy valid.csv tại {VALID_FILE}.")
    except Exception as ex_v:
        print(f"   ⚠️ Lỗi nạp mapping valid.csv: {ex_v}")

    # 3. Ánh xạ danh sách bưu cục sang sortcode tương ứng
    stations = []
    for name in station_names:
        name_clean = str(name).strip().upper()
        code = d_sortcode.get(name_clean)
        if not code:
            # Thử tìm tương đối (chứa tên)
            for k, v in d_sortcode.items():
                if name_clean in k or k in name_clean:
                    code = v
                    break
        if code:
            stations.append({
                'name': name.strip(),
                'code': code
            })
            
    print(f"   ✅ Chuẩn bị {len(stations)} bưu cục có sortcode để kéo song song.")

    all_records = []
    lock = threading.Lock()

    def fetch_one(station):
        # Payload JFS sử dụng cơ chế Code-Only (scanSiteCodeId và scanSiteCodeTypeId để trống)
        payload = {
            'beginDate': date_start, 'endDate': date_end,
            'nextNetworkCode': 'HCM004H',
            'nextStationCode': 'HCM004H', 'nextStationCodeId': 11888,
            'nextStationCodeName': 'HCM HUB', 'nextStationCodeTypeId': 335,
            'countryId': '1', 'size': 1000, 'sqlCode': 'realtime_sca_sen_mon_dtl',
            'wayType': '1',
            'scanSiteCode': station['code'],
            'scanSiteCodeId': '',
            'scanSiteCodeName': station['name'],
            'scanSiteCodeTypeId': '',
        }
        try:
            page = 1
            while True:
                list_payload = {**payload, 'paginationSearchType': 'list', 'current': page}
                r_list = auth_post(session, URL_ARRIVAL_SCAN, token_mgr, base_headers,
                                   params=ARRIVAL_PARAMS,
                                   json_body=list_payload,
                                   label=f'Arrival {station["name"]} p{page}')
                res_json = r_list.json()
                data_node = res_json.get('data')
                
                records = []
                if isinstance(data_node, dict):
                    records = data_node.get('records', []) or []
                elif isinstance(data_node, list):
                    records = data_node
                    
                if not records:
                    break
                    
                with lock:
                    all_records.extend(records)
                    
                if len(records) < 1000:
                    break
                page += 1
        except Exception as e:
            print(f'   ❌ Arrival {station["name"]}: {e}')

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(fetch_one, stations))

    if not all_records:
        print('   ⚠️ Arrival JFS: không có dữ liệu.')
        return []

    df = pd.DataFrame(all_records)
    # Tính Ngày vận hành (cycle 6h–6h)
    df['scantime_dt'] = pd.to_datetime(df.get('scantime'), errors='coerce')
    
    # Logic đặc biệt cho BN HUB: cộng thêm 36 giờ vào thời gian xuất phát
    # để khớp chính xác với chu kỳ di chuyển Bắc-Nam (~34-36 tiếng).
    if 'scansitename' in df.columns:
        is_bn_hub = df['scansitename'].astype(str).str.strip().str.upper() == 'BN HUB'
        df.loc[is_bn_hub, 'scantime_dt'] = df.loc[is_bn_hub, 'scantime_dt'] + pd.Timedelta(hours=36)
        df = df.rename(columns={'scansitename': 'Pickup_station'})
        
    df['Ngày vận hành'] = (df['scantime_dt'] - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
    df['Scan Hour']     = df['scantime_dt'].dt.hour.fillna(-1).astype(int)
    df = df.drop(columns=['scantime_dt'], errors='ignore')
    
    print(f'   ✅ Arrival raw: {len(df):,} dòng từ {len(stations)} bưu cục.')
    return df.to_dict(orient='records')


# ================================================================
# PULLERS
# ================================================================
def pull_forecast(session, token_mgr, headers, base_payload, label='Forecast'):
    page_size = 100 
    base_payload['size'] = page_size

    total = 0
    try:
        r = auth_post(session, URL_FORECAST_COUNT, token_mgr, headers,
                      data=base_payload, label='Forecast count')
        data = r.json()
        total = data.get('data') if isinstance(data.get('data'), int) else 0
        print(f"   ℹ️ {label} total: {total} đơn")
    except Exception as e:
        print(f"   ⚠️ Lỗi lấy total {label}: {e}")

    def fetch_page(p):
        payload = {**base_payload, 'current': p}
        r = auth_post(session, URL_FORECAST, token_mgr, headers, data=payload, label=label)
        return r.json().get('data', []) or []

    all_data = pull_pages_sequential(fetch_page, page_size, label, total=total, stop_short=True)

    return all_data


def pull_scan(session, token_mgr, url, headers, params, base_payload, label=''):
    page_size = int(base_payload.get('size', 1000))
    is_dynamic = "findByPagination" in url

    total = None
    if is_dynamic:
        try:
            count_payload = {**base_payload, 'paginationSearchType': 'count', 'size': 1}
            r = auth_post(session, url, token_mgr, headers, params=params,
                          json_body=count_payload, label=f'{label} count')
            t = r.json().get('data', {}).get('total', None)
            total = t if isinstance(t, int) else None
        except Exception as e:
            print(f"   ⚠️ {label} count: {e}")

    def fetch_page(p):
        payload = {**base_payload, 'current': p}
        if is_dynamic:
            payload['paginationSearchType'] = 'list'
        r = auth_post(session, url, token_mgr, headers, params=params, json_body=payload, label=label)
        data_obj = r.json().get('data', {})
        if not is_dynamic and isinstance(data_obj, dict):
            nonlocal total
            t = data_obj.get('total')
            if isinstance(t, int):
                total = t
        if isinstance(data_obj, dict):
            return data_obj.get('records', []) or []
        return []

    all_data = pull_pages_sequential(fetch_page, page_size, label, total=total, stop_short=True)

    if total is not None and len(all_data) < total:
        print(f"   ⚠️ {label}: thu {len(all_data)} < tổng {total} (có thể có trang lỗi)")
    print(f"   ✅ {label}: {len(all_data)}/{total if total is not None else '?'} dòng")
    return all_data


def pull_dispatch(session, token_mgr, headers, base_payload, label='Dispatch'):
    page_size = int(base_payload.get('size', 1000))

    def fetch_page(p):
        payload = {**base_payload, 'current': p}
        r = auth_post(session, URL_DISPATCH, token_mgr, headers, data=payload, label=label)
        obj = r.json().get('data', {})
        return (obj.get('records') or obj.get('list') or obj.get('rows') or []), obj

    try:
        records1, obj1 = fetch_page(1)
    except Exception as e:
        print(f"   ❌ Dispatch: {e}")
        print(f"   ✅ Dispatch: 0/? dòng")
        return []

    total = obj1.get('total', None)
    total = total if isinstance(total, int) else None
    all_data = list(records1)

    if records1:
        if total is not None and total > len(records1):
            rest = pull_pages_parallel(lambda p: fetch_page(p)[0], total, page_size, label, start_page=2)
            all_data.extend(rest)
        elif total is None:
            seq = pull_pages_sequential(lambda p: fetch_page(p)[0], page_size, label,
                                        total=None, stop_short=True, start_page=2)
            all_data.extend(seq)

    if total is not None and len(all_data) < total:
        print(f"   ⚠️ Dispatch: thu {len(all_data)} < tổng {total} (có thể có trang lỗi)")
    print(f"   ✅ Dispatch: {len(all_data)}/{total if total is not None else '?'} dòng")
    return all_data


# ================================================================
# UTILS
# ================================================================
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_valid(path):
    try:
        df = pd.read_csv(path, encoding='utf-8-sig', dtype=str)
        df.columns = df.columns.str.strip()
        print(f"   ✅ Valid: {len(df)} dòng | Cột: {list(df.columns)}")
        d_sortcode, d_buucuc, d_tuyen, d_rank = {}, {}, {}, {}
        if 'sortcode' in df.columns and 'Bưu cục final' in df.columns:
            d_sortcode = {str(k).strip(): str(v).strip() for k, v in df.set_index('sortcode')['Bưu cục final'].to_dict().items() if pd.notna(k) and str(k).strip() != '' and pd.notna(v) and str(v).strip() != ''}
        if 'Bưu cục' in df.columns and 'Bưu cục final' in df.columns:
            d_buucuc = {str(k).strip(): str(v).strip() for k, v in df.set_index('Bưu cục')['Bưu cục final'].to_dict().items() if pd.notna(k) and str(k).strip() != '' and pd.notna(v) and str(v).strip() != ''}
        if 'Bưu cục final' in df.columns:
            if 'Tuyến' in df.columns:
                d_tuyen = {str(k).strip(): str(v).strip() for k, v in df.set_index('Bưu cục final')['Tuyến'].to_dict().items() if pd.notna(k) and str(k).strip() != '' and pd.notna(v) and str(v).strip() != ''}
            if 'Rank' in df.columns:
                d_rank = {str(k).strip(): str(v).strip() for k, v in df.set_index('Bưu cục final')['Rank'].to_dict().items() if pd.notna(k) and str(k).strip() != '' and pd.notna(v) and str(v).strip() != ''}
        return d_sortcode, d_buucuc, d_tuyen, d_rank
    except FileNotFoundError:
        print(f"   ❌ Không tìm thấy: {path}")
        return {}, {}, {}, {}


def extract_ma10(val):
    if pd.isna(val) or str(val).strip() == '':
        return ''
    matches = re.findall(r'[A-Z]{2,3}\d{3}[A-Z0-9]', str(val))
    return matches[0] if matches else ''


def _cleanup_old_files(directory: str, keep_file: str):
    deleted = []
    for fname in os.listdir(directory):
        if not fname.endswith('.csv'):
            continue
        fpath = os.path.join(directory, fname)
        if os.path.abspath(fpath) == os.path.abspath(keep_file):
            continue
        try:
            os.remove(fpath)
            deleted.append(fname)
        except Exception as e:
            print(f"   ⚠️ Không xóa được '{fname}': {e}")
    if deleted:
        print(f"   🗑️  Đã xóa {len(deleted)} file cũ: {', '.join(deleted)}")


# ================================================================
# GOOGLE SHEETS SYNC
# ================================================================
def update_outbound_sheet(gc, master_chutes, outbound_volumes_grouped, target_dates):
    try:
        sheet = gc.open_by_key(SHEET_ID).worksheet("Outbound")
    except Exception:
        ss = gc.open_by_key(SHEET_ID)
        sheet = ss.add_worksheet("Outbound", rows=1000, cols=7)
        
    all_rows = sheet.get_all_values()
    headers = ["Zone", "AreaID", "Bưu cục", "Volume", "Weight", "Sức chứa", "Ngày"]
    
    new_rows = [headers]
    if all_rows:
        for r in all_rows[1:]:
            # Pad row if too short to prevent index errors
            while len(r) < len(all_rows[0]):
                r.append("")
            try:
                zone = r[0]
                area_id = r[1]
                name = r[2]
                vol = int(str(r[3]).replace(".", "").replace(",", ""))
                
                if len(r) == 7:
                    weight = int(str(r[4]).replace(".", "").replace(",", ""))
                    capacity = r[5]
                    date = r[6].strip()
                elif len(r) == 9:
                    weight = int(str(r[4]).replace(".", "").replace(",", ""))
                    capacity = r[7]
                    date = r[8].strip()
                elif len(r) == 8:
                    weight = 0
                    capacity = r[6]
                    date = r[7].strip()
                else:
                    continue
                
                if date in target_dates:
                    continue
                try:
                    date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                    if (datetime.now().date() - date_obj).days > 30:
                        continue
                except ValueError:
                    pass
                new_rows.append([zone, area_id, name, vol, weight, capacity, date])
            except Exception:
                pass
                
    for d_str in sorted(target_dates):
        for (zone, area_id), info in master_chutes.items():
            name_upper = info["name"].strip().upper()
            info_vol_wt = outbound_volumes_grouped.get((d_str, name_upper), {'volume': 0, 'weight': 0})
            vol = info_vol_wt['volume']
            weight = round(info_vol_wt['weight'])
            
            row = [""] * len(headers)
            row[0] = info["zone"]
            row[1] = info["area_id"]
            row[2] = info["name"]
            row[3] = vol
            row[4] = weight
            row[5] = info["capacity"]
            row[6] = d_str
            new_rows.append(row)
            
    sheet.clear()
    sheet.update(range_name="A1", values=new_rows)
    print(f"   ✅ Đã cập nhật sheet 'Outbound' cho các ngày: {list(target_dates)}")


def update_backlog_sheet(gc, master_chutes, backlog_volumes, current_date_str):
    try:
        sheet = gc.open_by_key(SHEET_ID).worksheet("Backlog")
    except Exception:
        ss = gc.open_by_key(SHEET_ID)
        sheet = ss.add_worksheet("Backlog", rows=1000, cols=7)
        
    headers = ["Zone", "AreaID", "Bưu cục", "Volume", "Weight", "Sức chứa", "Ngày"]
    
    new_rows = [headers]
    for (zone, area_id), info in master_chutes.items():
        name_upper = info["name"].strip().upper()
        info_vol_wt = backlog_volumes.get(name_upper, {'volume': 0, 'weight': 0})
        vol = info_vol_wt['volume']
        weight = round(info_vol_wt['weight'])
        row = [
            info["zone"],
            info["area_id"],
            info["name"],
            vol,
            weight,
            info["capacity"],
            current_date_str
        ]
        new_rows.append(row)
        
    sheet.clear()
    sheet.update(range_name="A1", values=new_rows)
    print(f"   ✅ Đã cập nhật sheet 'Backlog' pivoted với {len(new_rows)-1} dòng.")


def update_inventory_sheet(gc, master_chutes, inventory_volumes, current_date_str):
    try:
        sheet = gc.open_by_key(SHEET_ID).worksheet("Inventory")
    except Exception:
        ss = gc.open_by_key(SHEET_ID)
        sheet = ss.add_worksheet("Inventory", rows=1000, cols=8)
        
    headers = ["Zone", "AreaID", "Bưu cục", "Trạng thái", "Volume", "Weight", "Sức chứa", "Ngày"]
    statuses = ['Đang trên bãi', 'Đã lấy hàng', 'Đã điều phối bưu cục', 'Đã rời HUB']
    
    new_rows = [headers]
    for (zone, area_id), info in master_chutes.items():
        name_upper = info["name"].strip().upper()
        for status in statuses:
            info_vol_wt = inventory_volumes.get((name_upper, status), {'volume': 0, 'weight': 0})
            vol = info_vol_wt['volume']
            weight = round(info_vol_wt['weight'])
            row = [
                info["zone"],
                info["area_id"],
                info["name"],
                status,
                vol,
                weight,
                info["capacity"],
                current_date_str
            ]
            new_rows.append(row)
            
    sheet.clear()
    sheet.update(range_name="A1", values=new_rows)
    print(f"   ✅ Đã cập nhật sheet 'Inventory' pivoted với {len(new_rows)-1} dòng.")


def update_inbound_sheets(gc, results, master_chutes, d_buucuc):
    print("\n📥 Bắt đầu cập nhật dữ liệu Inbound gom nhóm theo trạng thái & khung giờ lên Google Sheets...")
    
    def write_sheet(sheet_name, df_data, headers):
        try:
            sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        except Exception:
            try:
                ss = gc.open_by_key(SHEET_ID)
                sheet = ss.add_worksheet(sheet_name, rows=1000, cols=len(headers))
            except Exception as e:
                print(f"   ❌ Không thể tạo sheet '{sheet_name}': {e}")
                raise e
        
        try:
            sheet.clear()
            if df_data.empty:
                rows = [headers]
            else:
                for h in headers:
                    if h not in df_data.columns:
                        df_data[h] = ""
                df_clean = df_data[headers].fillna("")
                rows = [headers] + df_clean.values.tolist()
                
            sheet.update(range_name='A1', values=rows)
            print(f"   ✅ Đã cập nhật Sheet '{sheet_name}' với {len(rows)-1} dòng.")
        except Exception as e:
            print(f"   ❌ Lỗi ghi dữ liệu lên sheet '{sheet_name}': {e}")
            raise e

    # Using module-level get_operating_date

    # Build dictionary of waybill -> forecast_time (dispatchNetworkTime) from Dispatch
    wb_to_forecast = {}
    df_dp_raw = pd.DataFrame(results.get('dispatch', []))
    if not df_dp_raw.empty:
        for _, r in df_dp_raw.iterrows():
            wb = str(r.get('waybillNo') or r.get('waybillId', '')).strip()
            pk = str(r.get('dispatchNetworkTime') or r.get('updateTime') or '').strip()
            if wb and pk and pk.lower() not in ('nan', 'none'):
                wb_to_forecast[wb] = pk
                
    # Build dictionary of waybill -> actual_pickup_time (deliveryTime) from Forecast sheet
    wb_to_pickup = {}
    df_fc_raw = pd.DataFrame(results.get('forecast', []))
    if not df_fc_raw.empty:
        for _, r in df_fc_raw.iterrows():
            wb = str(r.get('waybillNo', '')).strip()
            pk = str(r.get('deliveryTime') or '').strip()
            if wb and pk and pk.lower() not in ('nan', 'none'):
                wb_to_pickup[wb] = pk

    rows_to_aggregate = []
    
    # 1. Forecast
    if not df_fc_raw.empty:
        for _, r in df_fc_raw.iterrows():
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            waybill = str(r.get('waybillNo', '')).strip()
            w = float(r.get('loadWeight') or 0.0)
            t_ref = r.get('deliveryTime')
            # For Forecast, Actual Pickup Time is deliveryTime (from forecast)
            pick_time = str(r.get('deliveryTime') or '').strip()
            if fc_mapped and waybill:
                rows_to_aggregate.append({
                    'fc': fc_mapped,
                    'waybill': waybill,
                    'weight': w,
                    'status': 'Forecast',
                    'ib_date': '',
                    'forecast_time': wb_to_forecast.get(waybill, ''),  # dispatchNetworkTime từ Dispatch lookup
                    'pickup_time': pick_time,
                    'time_ref': t_ref
                })
                
    # 2. Dispatch
    if not df_dp_raw.empty:
        for _, r in df_dp_raw.iterrows():
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            waybill = str(r.get('waybillNo') or r.get('waybillId', '')).strip()
            w = float(r.get('packageChargeWeight') or 0.0)
            status = str(r.get('orderStatusName') or 'Dispatch').strip()
            t_ref = r.get('dispatchNetworkTime') or r.get('updateTime')
            # For Dispatch, use dispatchNetworkTime as the dispatch time reference
            fc_time = str(r.get('dispatchNetworkTime') or r.get('updateTime') or '').strip()
            pick_time = wb_to_pickup.get(waybill, '')
            if fc_mapped and waybill:
                rows_to_aggregate.append({
                    'fc': fc_mapped,
                    'waybill': waybill,
                    'weight': w,
                    'status': status if status != 'nan' else 'Dispatch',
                    'ib_date': '',
                    'forecast_time': fc_time,
                    'pickup_time': pick_time,
                    'time_ref': t_ref
                })

    # 3. Inbound
    df_in_raw = pd.DataFrame(results.get('inbound', []))
    if not df_in_raw.empty:
        for _, r in df_in_raw.iterrows():
            fc = str(r.get('sendSite', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            waybill = str(r.get('billNo') or r.get('waybillNo', '')).strip()
            w = float(r.get('weight') or 0.0)
            ib_date = str(r.get('scanDate', '')).strip()
            pick_time = wb_to_pickup.get(waybill, '')
            fc_time = wb_to_forecast.get(waybill, '')
            if fc_mapped and waybill:
                rows_to_aggregate.append({
                    'fc': fc_mapped,
                    'waybill': waybill,
                    'weight': w,
                    'status': 'Arrival',
                    'ib_date': ib_date,
                    'forecast_time': fc_time,
                    'pickup_time': pick_time,
                    'time_ref': ib_date
                })

    # Merge / Deduplicate by waybill (highest status: Arrival > Dispatch > Forecast)
    status_priority = {'Arrival': 3, 'Inbound': 2.5, 'Dispatch': 2, 'Forecast': 1}
    
    unique_waybills = {}
    for r in rows_to_aggregate:
        wb = r['waybill']
        stat = r['status']
        priority = status_priority.get(stat, 0)
        
        if 'arrival' in stat.lower() or 'đến' in stat.lower():
            stat = 'Arrival'
            priority = 3
            
        if wb not in unique_waybills or priority > status_priority.get(unique_waybills[wb]['status'], 0):
            unique_waybills[wb] = r
            
    # Group by fc, status, op_date, hourly ib_date, hourly forecast_time, and hourly pickup_time
    grouped = {}
    now_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    
    for wb, r in unique_waybills.items():
        fc_name = r['fc']
        status = r['status']
        
        # Simple Inbound status logic:
        # If ib_date exists -> "Đã về Hub"
        # Else -> "Chưa về Hub"
        if r['ib_date'] and str(r['ib_date']).strip() not in ('', 'nan', 'None'):
            status_clean = 'Đã về Hub'
            ib_date_str = r['ib_date']
            try:
                dt_ib = pd.to_datetime(ib_date_str)
                ib_hour = int(dt_ib.hour)
                op_date = get_operating_date(dt_ib)
            except Exception:
                ib_hour = ""
                op_date = get_operating_date(now_vn)
        else:
            status_clean = 'Chưa về Hub'
            ib_hour = ""
            
            # Đối với đơn Chưa về Hub (lũy kế tồn đọng), ta luôn gán ngày vận hành hiện tại
            op_date = get_operating_date(now_vn)
                
        # Format pickup time to hour index 0-23
        pk_time_str = r['pickup_time']
        if pk_time_str and str(pk_time_str).strip() not in ('', 'nan', 'None'):
            try:
                dt_pk = pd.to_datetime(pk_time_str)
                pk_hour = int(dt_pk.hour)
            except Exception:
                pk_hour = ""
        else:
            pk_hour = ""

        # Format forecast time to hour index 0-23
        fc_time_str = r['forecast_time']
        if fc_time_str and str(fc_time_str).strip() not in ('', 'nan', 'None'):
            try:
                dt_fc = pd.to_datetime(fc_time_str)
                fc_hour = int(dt_fc.hour)
            except Exception:
                fc_hour = ""
        else:
            fc_hour = ""

        # Xác định loại rớt cho tất cả các đơn Forecast (Cả Chưa về Hub và Đã về Hub)
        loai_rot = ""
        # Fallback sử dụng time_ref (deliveryTime của Forecast) nếu forecast_time bị rỗng
        ref_time_to_use = fc_time_str if (fc_time_str and str(fc_time_str).strip() not in ('', 'nan', 'None')) else r['time_ref']
        
        if ref_time_to_use and str(ref_time_to_use).strip() not in ('', 'nan', 'None'):
            try:
                dt_fc = pd.to_datetime(ref_time_to_use)
                op_date_dt = pd.to_datetime(op_date)
                
                # 1. Nếu ngày điều phối nhỏ hơn ngày vận hành hiện tại -> Rớt hôm trước
                if dt_fc.date() < op_date_dt.date():
                    loai_rot = "Rớt hôm trước"
                # 2. Nếu cùng ngày vận hành, so sánh với mốc 06:00:00 sáng
                else:
                    threshold_dt = op_date_dt + timedelta(hours=6)
                    if dt_fc < threshold_dt:
                        loai_rot = "Rớt hôm trước"
                    else:
                        loai_rot = "Rớt hôm nay"
            except Exception:
                loai_rot = "Rớt hôm nay"
        else:
            loai_rot = "Rớt hôm nay"

        key = (fc_name, status_clean, op_date, ib_hour, fc_hour, pk_hour, loai_rot)
        if key not in grouped:
            grouped[key] = {'volume': 0, 'weight': 0.0}
        grouped[key]['volume'] += 1
        grouped[key]['weight'] += r['weight']
        
    # Convert grouped to DataFrame
    final_rows = []
    
    for (fc_name, status, op_date, ib_hour, fc_hour, pk_hour, loai_rot), stats in grouped.items():
        final_rows.append({
            'Bưu cục': fc_name,
            'Trạng thái': status,
            'Volume': stats['volume'],
            'Weight': int(stats['weight']),
            'Ngày vận hành': op_date,
            'Inbound Hour': ib_hour,
            'Forecast Time': fc_hour,
            'Pickup Time': pk_hour,
            'Loại rớt': loai_rot
        })
        
    df_inbound_aggregated = pd.DataFrame(final_rows)
    write_sheet("Inbound", df_inbound_aggregated, ["Bưu cục", "Trạng thái", "Volume", "Weight", "Ngày vận hành", "Inbound Hour", "Forecast Time", "Pickup Time", "Loại rớt"])

    # 4. Linehaul (Gộp các dòng trùng Phiếu nhiệm vụ con để kết hợp thông tin gửi & dỡ)
    df_lh_raw = pd.DataFrame(results.get('linehaul', []))
    df_lh = pd.DataFrame()
    if not df_lh_raw.empty:
        # Chuẩn hóa cột
        for col in ['traceCode', 'traceSubCode', 'sendTime', 'loadingEndTime', 'endNetworkName', 'startNetworkName', 'nextNetworkName', 'unloadingStartTime', 'unloadingEndTime', 'unloadingBillPiece', 'unloadingWeight', 'billPiece', 'totalBillPiece', 'loadBillPiece', 'weight', 'totalWeight', 'loadWeight']:
            if col not in df_lh_raw.columns:
                df_lh_raw[col] = None
        
        # Chọn các cột sản lượng gửi
        bill_col = 'unloadingBillPiece'
        if 'billPiece' in df_lh_raw.columns and df_lh_raw['billPiece'].notna().any():
            bill_col = 'billPiece'
        elif 'totalBillPiece' in df_lh_raw.columns and df_lh_raw['totalBillPiece'].notna().any():
            bill_col = 'totalBillPiece'
        elif 'loadBillPiece' in df_lh_raw.columns and df_lh_raw['loadBillPiece'].notna().any():
            bill_col = 'loadBillPiece'
            
        weight_col = 'unloadingWeight'
        if 'weight' in df_lh_raw.columns and df_lh_raw['weight'].notna().any():
            weight_col = 'weight'
        elif 'totalWeight' in df_lh_raw.columns and df_lh_raw['totalWeight'].notna().any():
            weight_col = 'totalWeight'
        elif 'loadWeight' in df_lh_raw.columns and df_lh_raw['loadWeight'].notna().any():
            weight_col = 'loadWeight'
        
        df_lh_raw['billPiece_clean'] = pd.to_numeric(df_lh_raw[bill_col], errors='coerce').fillna(0)
        df_lh_raw['weight_clean'] = pd.to_numeric(df_lh_raw[weight_col], errors='coerce').fillna(0)
        df_lh_raw['unloadingBillPiece_clean'] = pd.to_numeric(df_lh_raw['unloadingBillPiece'], errors='coerce').fillna(0)
        df_lh_raw['unloadingWeight_clean'] = pd.to_numeric(df_lh_raw['unloadingWeight'], errors='coerce').fillna(0)
        
        # Tạo hàm lấy nextNetworkName (StartNetworkName) nếu đi đến HCM HUB
        def get_next_network_val(row):
            end_net = str(row.get('endNetworkName') or '').strip()
            start_net = str(row.get('startNetworkName') or '').strip()
            next_net = str(row.get('nextNetworkName') or '').strip()
            is_dest_hcm = 'HCM' in end_net.upper() or 'SR0001' in end_net.upper() or 'HCM' in next_net.upper() or 'SR0001' in next_net.upper()
            if is_dest_hcm:
                return d_buucuc.get(start_net, start_net)
            return ''
            
        df_lh_raw['nextNetworkName_clean'] = df_lh_raw.apply(get_next_network_val, axis=1)

        # Định nghĩa hàm gộp (chọn giá trị không rỗng/lớn nhất)
        def aggregate_lh(group):
            # Lấy dòng có thông tin gửi
            send_t = group['sendTime'].dropna().str.strip().replace('', None).dropna()
            send_val = send_t.iloc[0] if not send_t.empty else ''
            
            load_et = group['loadingEndTime'].dropna().str.strip().replace('', None).dropna()
            load_val = load_et.iloc[0] if not load_et.empty else ''
            
            # Lấy dòng có thông tin dỡ
            ust = group['unloadingStartTime'].dropna().str.strip().replace('', None).dropna()
            ust_val = ust.iloc[0] if not ust.empty else ''
            
            uet = group['unloadingEndTime'].dropna().str.strip().replace('', None).dropna()
            uet_val = uet.iloc[0] if not uet.empty else ''
            
            # Lấy FC gửi lớn nhất hoặc không rỗng
            fc_names = group['nextNetworkName_clean'].dropna().str.strip().replace('', None).dropna()
            fc_val = fc_names.iloc[0] if not fc_names.empty else ''
            
            # Lấy sản lượng max hoặc sum phù hợp
            b_piece = group['billPiece_clean'].max()
            wt = group['weight_clean'].max()
            un_piece = group['unloadingBillPiece_clean'].max()
            un_wt = group['unloadingWeight_clean'].max()
            
            # Tính ngày vận hành
            ust_valid = ust_val if ust_val.lower() not in ('', 'nan', 'none') else ''
            uet_valid = uet_val if uet_val.lower() not in ('', 'nan', 'none') else ''
            send_valid = send_val if send_val.lower() not in ('', 'nan', 'none') else ''
            load_valid = load_val if load_val.lower() not in ('', 'nan', 'none') else ''
            
            dt_src = ust_valid if ust_valid else (uet_valid if uet_valid else (send_valid if send_valid else load_valid))
            op_date = get_operating_date(dt_src)
            
            return pd.Series({
                'Phiếu nhiệm vụ': group['traceCode'].dropna().iloc[0] if not group['traceCode'].dropna().empty else '',
                'sendTime': send_val,
                'loadingEndTime': load_val,
                'nextNetworkName': fc_val,
                'unloadingStartTime': ust_val,
                'unloadingEndTime': uet_val,
                'unloadingBillPiece': un_piece,
                'unloadingWeight': un_wt,
                'billPiece': b_piece,
                'weight': wt,
                'Ngày vận hành': op_date
            })

        # Gộp theo traceSubCode (Phiếu nhiệm vụ con)
        df_lh = df_lh_raw.groupby('traceSubCode', as_index=False).apply(aggregate_lh)
        df_lh.rename(columns={'traceSubCode': 'Phiếu nhiệm vụ con'}, inplace=True)
        
        # Chỉ giữ lại các dòng đi về HCM HUB (nextNetworkName không rỗng)
        df_lh = df_lh[df_lh['nextNetworkName'].astype(str).str.strip() != '']

    write_sheet("Linehaul", df_lh, ["Phiếu nhiệm vụ", "Phiếu nhiệm vụ con", "sendTime", "loadingEndTime", "nextNetworkName", "unloadingStartTime", "unloadingEndTime", "unloadingBillPiece", "unloadingWeight", "billPiece", "weight", "Ngày vận hành"])

    # 5. Arrival sheet (giám sát phát hàng – tích lũy theo ngày, trạm, giờ)
    arrival_raw = results.get('arrival', [])
    if arrival_raw:
        print("\n📋 Xử lý sheet Arrival...")
        df_arr = pd.DataFrame(arrival_raw)
        # Mapping "Đã đến Hub" / "Chưa đến Hub" bằng cách đối chiếu billcode vs billNo Inbound
        df_in_raw = pd.DataFrame(results.get('inbound', []))
        inbound_billnos = set()
        if not df_in_raw.empty:
            bn_col = 'billNo' if 'billNo' in df_in_raw.columns else ('waybillNo' if 'waybillNo' in df_in_raw.columns else None)
            if bn_col:
                inbound_billnos = set(df_in_raw[bn_col].dropna().astype(str).str.strip())
        bc_col = 'billcode' if 'billcode' in df_arr.columns else ('billNo' if 'billNo' in df_arr.columns else None)
        if bc_col and inbound_billnos:
            df_arr['Đã đến Hub']   = df_arr[bc_col].astype(str).str.strip().isin(inbound_billnos).astype(int)
            df_arr['Chưa đến Hub'] = 1 - df_arr['Đã đến Hub']
        else:
            df_arr['Đã đến Hub']   = 0
            df_arr['Chưa đến Hub'] = 1

        # Pivot: group by Ngày vận hành + Pickup_station + Scan Hour
        try:
            df_arr['scantime_dt'] = pd.to_datetime(df_arr.get('scantime'), errors='coerce')
            bill_col_agg = bc_col if bc_col else 'Đã đến Hub'
            df_pivot = df_arr.groupby(['Ngày vận hành', 'Pickup_station', 'Scan Hour']).agg(
                **{
                    'Tổng số đơn':  (bill_col_agg, 'size'),
                    'Đã đến Hub':   ('Đã đến Hub', 'sum'),
                    'Chưa đến Hub': ('Chưa đến Hub', 'sum'),
                    'Last_time_dt': ('scantime_dt', 'max'),
                }
            ).reset_index()
            df_pivot['Last time'] = df_pivot['Last_time_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
            df_pivot = df_pivot.drop(columns=['Last_time_dt'])
        except Exception as e_piv:
            print(f'   ⚠️ Arrival pivot lỗi: {e_piv}')
            df_pivot = pd.DataFrame()

        if not df_pivot.empty:
            # Đọc dữ liệu Arrival cũ từ Google Sheets để upsert tích lũy
            arrival_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour',
                            'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub', 'Last time']
            try:
                arr_sheet = gc.open_by_key(SHEET_ID).worksheet('Arrival')
            except Exception:
                try:
                    ss = gc.open_by_key(SHEET_ID)
                    arr_sheet = ss.add_worksheet('Arrival', rows=5000, cols=len(arrival_cols))
                except Exception as e_cr:
                    print(f'   ❌ Không thể tạo sheet Arrival: {e_cr}')
                    arr_sheet = None

            if arr_sheet:
                try:
                    old_vals = arr_sheet.get_all_values()
                    if len(old_vals) > 1:
                        df_old = pd.DataFrame(old_vals[1:], columns=old_vals[0])
                        for col in ['Scan Hour', 'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub']:
                            if col in df_old.columns:
                                df_old[col] = pd.to_numeric(df_old[col], errors='coerce').fillna(0).astype(int)
                        # Xóa dữ liệu cùng ngày để upsert với dữ liệu mới nhất
                        today_dates = set(df_pivot['Ngày vận hành'].unique())
                        df_old = df_old[~df_old['Ngày vận hành'].isin(today_dates)]
                        df_final = pd.concat([df_old, df_pivot[arrival_cols]], ignore_index=True)
                    else:
                        df_final = df_pivot[arrival_cols].copy()
                    # Sắp xếp: ngày mới nhất lên đầu
                    df_final = df_final.sort_values(
                        by=['Ngày vận hành', 'Pickup_station', 'Scan Hour'],
                        ascending=[False, True, True]
                    )
                    # Giới hạn 7 ngày gần nhất
                    all_dates = sorted(df_final['Ngày vận hành'].unique(), reverse=True)
                    df_final = df_final[df_final['Ngày vận hành'].isin(all_dates[:7])]
                    # Ghi lên Google Sheets
                    rows_to_write = [arrival_cols] + df_final[arrival_cols].fillna('').values.tolist()
                    arr_sheet.clear()
                    arr_sheet.update(range_name='A1', values=rows_to_write)
                    print(f'   ✅ Sheet Arrival: {len(rows_to_write)-1} dòng (lịch sử 7 ngày).')
                except Exception as e_write:
                    print(f'   ❌ Lỗi ghi sheet Arrival: {e_write}')
    else:
        print('   ⚠️ Không có dữ liệu Arrival để ghi sheet.')


def update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, current_date_str, results=None, d_buucuc=None):
    print(f"\n📊 Bắt đầu cập nhật dữ liệu Google Sheets...")
    
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    local_creds_path = r"C:\Users\lehoa\OneDrive\Desktop\testing\addressproject.json"
    
    # Sử dụng local json nếu không có biến môi trường
    if not creds_json and os.path.exists(local_creds_path):
        try:
            with open(local_creds_path, 'r', encoding='utf-8') as f:
                creds_json = f.read()
            print("   🔑 Đã tự động nạp Google Service Account từ file local addressproject.json trên Desktop.")
        except Exception as e_ld:
            print(f"   ⚠️ Lỗi đọc file addressproject.json: {e_ld}")

    if not creds_json:
        print("❌ Không tìm thấy biến môi trường GOOGLE_SERVICE_ACCOUNT_JSON hoặc file credentials local. Bỏ qua ghi Sheet.")
        return
        
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
        gc = gspread.authorize(creds)
        
        # Load master chutes from sheet1 (first sheet)
        master_chutes = {}
        try:
            first_sheet = gc.open_by_key(SHEET_ID).sheet1
            all_rows = first_sheet.get_all_values()
            if all_rows and len(all_rows) > 1:
                headers = all_rows[0]
                col_zone = headers.index("Zone") if "Zone" in headers else 0
                col_area = headers.index("AreaID") if "AreaID" in headers else 1
                col_name = headers.index("Bưu cục") if "Bưu cục" in headers else 2
                col_len = headers.index("Dài") if "Dài" in headers else 4
                col_wid = headers.index("Rộng") if "Rộng" in headers else 5
                col_cap = headers.index("Sức chứa") if "Sức chứa" in headers else 6
                
                for r in all_rows[1:]:
                    if len(r) > max(col_zone, col_area, col_name):
                        zone = r[col_zone].strip()
                        area_id = r[col_area].strip()
                        name = r[col_name].strip()
                        if zone and area_id and name:
                            key = (zone, area_id)
                            if key not in master_chutes:
                                master_chutes[key] = {
                                    "zone": zone,
                                    "area_id": area_id,
                                    "name": name,
                                    "dai": r[col_len] if col_len < len(r) else "8",
                                    "rong": r[col_wid] if col_wid < len(r) else "4",
                                    "capacity": r[col_cap] if col_cap < len(r) else "780"
                                }
        except Exception as ex:
            print(f"   ⚠️ Không thể load cấu hình bưu cục từ sheet1: {ex}")
            
        # Fallback to valid.csv
        if not master_chutes:
            print("   ℹ| Load cấu hình bưu cục mặc định từ valid.csv...")
            try:
                df_valid = pd.read_csv(VALID_FILE, encoding='utf-8-sig', dtype=str)
                df_valid.columns = df_valid.columns.str.strip()
                col_z = 'Zone'
                col_a = 'area' if 'area' in df_valid.columns else 'Area'
                col_n = 'Bưu cục final' if 'Bưu cục final' in df_valid.columns else 'Bưu cục'
                
                for _, row in df_valid.iterrows():
                    zone = str(row.get(col_z, '')) if col_z in row else 'A' # fallback zone
                    area_id = str(row.get(col_a, '')).strip()
                    name = str(row.get(col_n, '')).strip()
                    if zone and area_id and name and name.lower() != 'nan':
                        key = (zone, area_id)
                        if key not in master_chutes:
                            master_chutes[key] = {
                                "zone": zone,
                                "area_id": area_id,
                                "name": name,
                                "dai": "8",
                                "rong": "4",
                                "capacity": "780"
                            }
            except Exception as ex2:
                print(f"   ❌ Lỗi load fallback từ valid.csv: {ex2}")
                
        # 1. Update Outbound Sheet
        if run_outbound and target_dates:
            update_outbound_sheet(gc, master_chutes, outbound_volumes_grouped, target_dates)
            
        # 2. Update Backlog Sheet (Realtime Pivot)
        if run_backlog_inv:
            backlog_volumes = {}
            try:
                conn = sqlite3.connect(DB_FILE)
                # Đọc trực tiếp các đơn có status 'Đang trên bãi' từ SQLite
                df_db_bl = pd.read_sql_query(
                    "SELECT next_station, weight, waybillNo FROM inventory WHERE status_order = 'Đang trên bãi'", 
                    conn
                )
                conn.close()
                if not df_db_bl.empty:
                    df_db_bl['next_station_upper'] = df_db_bl['next_station'].astype(str).str.strip().str.upper()
                    backlog_volumes = df_db_bl.groupby('next_station_upper').agg(
                        volume=('waybillNo', 'size'),
                        weight=('weight', 'sum')
                    ).to_dict(orient='index')
            except Exception as e_bl_db:
                print(f"   ⚠️ Lỗi tính Backlog pivot từ SQLite: {e_bl_db}")
            update_backlog_sheet(gc, master_chutes, backlog_volumes, current_date_str)
            
        # 3. Update Inventory Sheet (Realtime Pivot)
        if run_backlog_inv:
            inventory_volumes = {}
            try:
                conn = sqlite3.connect(DB_FILE)
                # Đọc toàn bộ inventory từ SQLite
                df_db_inv = pd.read_sql_query(
                    "SELECT next_station, status_order, weight, waybillNo, time_ref FROM inventory", 
                    conn
                )
                conn.close()
                if not df_db_inv.empty:
                    # Chỉ lọc ngày vận hành hiện tại đối với đơn 'Đã rời HUB'. 
                    # Các đơn chưa xuất kho (Đang trên bãi, Đã lấy hàng, Đã điều phối) thì giữ lại toàn bộ để tính tồn đọng thực tế.
                    def filter_inventory_dates(row):
                        status = str(row['status_order']).strip()
                        if status == 'Đã rời HUB':
                            t_ref = row['time_ref']
                            row_op = get_operating_date(t_ref) if (t_ref and str(t_ref).strip() not in ('', 'nan', 'None')) else current_date_str
                            return row_op == current_date_str
                        return True
                        
                    df_db_inv = df_db_inv[df_db_inv.apply(filter_inventory_dates, axis=1)]
                    df_db_inv['next_station_upper'] = df_db_inv['next_station'].astype(str).str.strip().str.upper()
                    df_db_inv['status_upper'] = df_db_inv['status_order'].astype(str).str.strip()
                    
                    inventory_volumes = df_db_inv.groupby(['next_station_upper', 'status_upper']).agg(
                        volume=('waybillNo', 'size'),
                        weight=('weight', 'sum')
                    ).to_dict(orient='index')
            except Exception as e_inv_db:
                print(f"   ⚠️ Lỗi tính Inventory pivot từ SQLite: {e_inv_db}")
            update_inventory_sheet(gc, master_chutes, inventory_volumes, current_date_str)
            
        # 4. Update Inbound Sheets (aggregated Inbound + raw Linehaul + Arrival)
        if results:
            update_inbound_sheets(gc, results, master_chutes, d_buucuc)
            
    except Exception as e:
        print(f"   ❌ Lỗi cập nhật Google Sheets: {e}")
        raise e

# ================================================================
# MAIN (Run Once)
# ================================================================
def sync_valid_from_sheets(gc):
    print("   📥 Đồng bộ valid.csv từ Google Sheet...")
    try:
        sheet = gc.open_by_key(SHEET_ID).worksheet("valid")
        rows = sheet.get_all_values()
        if len(rows) > 1:
            df = pd.DataFrame(rows[1:], columns=rows[0])
            df.to_csv(VALID_FILE, index=False, encoding='utf-8-sig')
            print(f"      ✅ Đã cập nhật local valid.csv với {len(df)} dòng từ Google Sheets.")
    except Exception as e:
        print(f"      ⚠️ Không thể đồng bộ valid.csv từ Google Sheet: {e}. Sử dụng file local hiện có.")


def run_once(session, token_mgr, rebuild_days=None):
    from zoneinfo import ZoneInfo
    tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
    now = datetime.now(tz_vn)

    is_rebuild = rebuild_days is not None
    
    if is_rebuild:
        print(f"🔄 ĐANG CHẠY CHẾ ĐỘ REBUILD: {rebuild_days} ngày")
        DATE_START = (now - timedelta(days=rebuild_days)).strftime('%Y-%m-%d') + ' 06:00:00'
        DATE_END   = now.strftime('%Y-%m-%d %H:%M:%S')  # Query up to current second
        run_outbound = True
        run_backlog_inv = True
    else:
        # Chạy 24/7 để đảm bảo dữ liệu luôn được đồng bộ khi có kích hoạt hoặc chạy định kỳ
        DATE_START = (now - timedelta(days=2)).strftime('%Y-%m-%d') + ' 06:00:00'
        DATE_END   = now.strftime('%Y-%m-%d %H:%M:%S')  # Query up to current second
        run_outbound = True
        run_backlog_inv = True

    # Sync valid config sheet if possible
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
            gc_init = gspread.authorize(creds)
            sync_valid_from_sheets(gc_init)
        except Exception as e:
            print(f"   ⚠️ Lỗi kết nối Google Sheets khi đồng bộ valid: {e}")

    print("\n" + "=" * 60)
    print(f"🕐 Bắt đầu : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Range   : {DATE_START} → {DATE_END}")
    print("=" * 60)

    # Copy external valid.csv if exists
    external_valid = r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv"
    if os.path.exists(external_valid):
        import shutil
        try:
            shutil.copy2(external_valid, VALID_FILE)
            print(f"   🔄 Tự động đồng bộ valid.csv từ Desktop: {external_valid}")
        except Exception as e:
            print(f"   ⚠️ Lỗi đồng bộ valid.csv từ Desktop: {e}")

    print("\n📋 Load valid.csv...")
    d_sortcode, d_buucuc, d_tuyen, d_rank = load_valid(VALID_FILE)

    print("\n🔐 Kiểm tra token (in-memory)...")
    if not token_mgr.get_token():
        print("❌ Không lấy được token.")
        return

    # Khởi tạo token manager riêng biệt cho nguồn Arrival sử dụng tài khoản 660085
    print("🔐 Khởi tạo TokenManager riêng biệt cho Arrival (User: 660085)...")
    arrival_token_mgr = TokenManager(session, "660085", "246@Hoang", COUNTRY_ID)
    try:
        arrival_token_mgr.get_token()
    except Exception as e_login_arr:
        print(f"⚠️ Lỗi login tài khoản 660085 cho Arrival: {e_login_arr}. Sẽ tự động thử lại khi chạy.")

    fh = load_json(os.path.join(BASE_DIR, "config", "forecastheaders.json"))
    fp = load_json(os.path.join(BASE_DIR, "config", "forecastpayload.json"))
    for k in ['timeStart', 'inputTimeStart']: fp[k] = DATE_START
    for k in ['timeEnd', 'inputTimeEnd']:     fp[k] = DATE_END

    ih = load_json(os.path.join(BASE_DIR, "config", "inboundheaders.json"))
    ip = load_json(os.path.join(BASE_DIR, "config", "inboundpayload.json"))
    ip['beginDate'] = DATE_START; ip['endDate'] = DATE_END
    i_params = {'sqlCode': ip.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': ih.get('routeName', '')}

    oh = load_json(os.path.join(BASE_DIR, "config", "outboundheaders.json"))
    op = load_json(os.path.join(BASE_DIR, "config", "outboundpayload.json"))
    op['beginDate'] = DATE_START; op['endDate'] = DATE_END
    o_params = {'sqlCode': op.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': oh.get('routeName', '')}

    bh = load_json(os.path.join(BASE_DIR, "config", "backlogheaders.json"))
    bp = load_json(os.path.join(BASE_DIR, "config", "backlogpayload.json"))
    if bp.get('endDate', '').upper() == 'AUTO': bp['endDate'] = DATE_END
    b_params = {'sqlCode': bp.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': bh.get('routeName', '')}

    dh = load_json(os.path.join(BASE_DIR, "config", "dispatchheaders.json"))
    dp_cfg = load_json(os.path.join(BASE_DIR, "config", "dispatchpayload.json"))
    dp_cfg['startInputTime'] = DATE_START; dp_cfg['endInputTime'] = DATE_END

    lh_h = load_json(os.path.join(BASE_DIR, "config", "linehaulheaders.json"))
    lh_p = load_json(os.path.join(BASE_DIR, "config", "linehaulpayload.json"))
    lh_p['startScanTime'] = DATE_START
    lh_p['endScanTime'] = DATE_END
    lh_params = {'sqlCode': lh_p.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': lh_h.get('routeName', '')}

    print("\n🚀 Kéo data song song...")
    results = {}
    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
        futures = {
            ex.submit(pull_forecast, session, token_mgr, fh, fp): 'forecast',
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, ih, i_params, ip, 'Inbound'): 'inbound',
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, bh, b_params, bp, 'Backlog'): 'backlog',
            ex.submit(pull_dispatch, session, token_mgr, dh, dp_cfg): 'dispatch',
            ex.submit(pull_scan, session, token_mgr, URL_LINEHAUL, lh_h, lh_params, lh_p, 'Linehaul'): 'linehaul',
            ex.submit(pull_arrival_from_jfs, session, arrival_token_mgr, ih, DATE_START, DATE_END): 'arrival',
        }
        if run_outbound:
            futures[ex.submit(pull_scan, session, token_mgr, URL_SCAN, oh, o_params, op, 'Outbound')] = 'outbound'

        for f in as_completed(futures):
            key = futures[f]
            try:
                results[key] = f.result()
            except Exception as e:
                print(f"   ⚠️ {key} lỗi: {e}")
                results[key] = []

    print("\n🔗 Xử lý & join data...")

    SYSTEM_STATUSES = {
        'Lấy hàng thất bại',
        'Đã điều phối nhân viên',
        'Đã điều phối bưu cục',
    }

    DISPATCH_PRESERVE_STATUSES = {
        'Đang giao hàng',
        'Đã giao hàng',
        'Giao hàng thất bại',
        'Hoàn hàng',
        'Đang hoàn hàng',
        'Đã hủy',
        'Đã điều phối nhân viên',
        'Đã điều phối bưu cục',
        'Lấy hàng thất bại',
    }

    # ================================================================
    # DISPATCH
    # ================================================================
    df_dp_raw = pd.DataFrame(results.get('dispatch', []))
    df_dp_lookup = pd.DataFrame()

    if not df_dp_raw.empty:
        dp_cols = ['waybillId', 'dispatchNetworkName', 'pickNetworkName',
                   'terminalDispatchCode', 'orderStatusName', 'packageChargeWeight',
                   'dispatchNetworkTime', 'updateTime']
        dp_cols = [c for c in dp_cols if c in df_dp_raw.columns]
        df_dp_raw = df_dp_raw[dp_cols].copy()
        df_dp_raw.rename(columns={
            'waybillId':           'waybillNo',
            'dispatchNetworkName': 'dispatch_plan',
            'orderStatusName':     'status_order',
            'packageChargeWeight': 'weight'
        }, inplace=True)

        if 'status_order' in df_dp_raw.columns:
            df_dp_raw = df_dp_raw[df_dp_raw['status_order'] != 'Đã hủy']

        df_dp_lookup = df_dp_raw.copy()
        if 'updateTime' in df_dp_lookup.columns:
            df_dp_lookup['updateTime'] = pd.to_datetime(df_dp_lookup['updateTime'], errors='coerce')
            df_dp_lookup = df_dp_lookup.sort_values('updateTime').groupby('waybillNo', as_index=False).last()
        else:
            df_dp_lookup = df_dp_lookup.drop_duplicates(subset='waybillNo', keep='last')

        if 'terminalDispatchCode' in df_dp_lookup.columns:
            df_dp_lookup['next_station'] = df_dp_lookup['terminalDispatchCode'].apply(extract_ma10).map(d_sortcode).fillna('')
        else:
            df_dp_lookup['next_station'] = ''

        df_dp_lookup['data_source'] = 'Dispatch'
        df_dp_lookup['waybillNo'] = df_dp_lookup['waybillNo'].astype(str).str.strip()
        print(f"   ✅ Dispatch lookup: {len(df_dp_lookup)} đơn unique")

    # ================================================================
    # FORECAST
    # ================================================================
    df_fc = pd.DataFrame(results.get('forecast', []))
    if not df_fc.empty:
        fc_cols = ['waybillNo', 'dispatchNetworkName', 'pickNetworkName', 'loadWeight', 'deliveryTime']
        fc_cols = [c for c in fc_cols if c in df_fc.columns]
        df_fc = df_fc[fc_cols].copy()
        df_fc.rename(columns={
            'dispatchNetworkName': 'dispatch_plan',
            'loadWeight':          'weight',
            'deliveryTime':        'Pickup_time'
        }, inplace=True)
        df_fc.drop_duplicates(subset='waybillNo', keep='last', inplace=True)
        df_fc['data_source']  = 'Forecast'
        df_fc['status_order'] = ''
        df_fc['next_station'] = df_fc['dispatch_plan'].map(d_buucuc).fillna('')
        df_fc['dispatchNetworkTime'] = df_fc['Pickup_time']  # dùng deliveryTime làm fallback cho Forecast
        df_fc['time_ref']            = df_fc['Pickup_time']
    print(f"   Forecast unique: {len(df_fc)}")

    # ================================================================
    # BACKLOG
    # ================================================================
    BACKLOG_REDELIVER_REMARKS = {
        'Người nhận từ chối nhận hàng',
        'Khách không ở địa chỉ giao hàng',
        'Số điện thoại không liên lạc được',
        'Người nhận đặt trùng đơn / mua nhầm',
        'Khách từ chối thanh toán',
        'Khách không đặt hàng',
        'Sai số điện thoại',
        'Khách yêu cầu dùng thử, kiểm hàng',
        'Người nhận hẹn lại thời gian giao hàng',
        'Địa chỉ khách hàng sai',
        'Hàng hóa hư hỏng một phần',
        'Hàng hóa hư hỏng hoàn toàn'
    }

    df_bl = pd.DataFrame(results.get('backlog', []))
    if not df_bl.empty:
        if 'operate_site_type' in df_bl.columns:
            df_bl = df_bl[df_bl['operate_site_type'] == 'Trong kho']

        bl_cols = ['billcode', 'take_site_name', 'destination_site_name', 'weight', 'abnormal_remark']
        bl_cols = [c for c in bl_cols if c in df_bl.columns]
        df_bl = df_bl[bl_cols].copy()

        if 'abnormal_remark' in df_bl.columns:
            is_redeliver = df_bl['abnormal_remark'].isin(BACKLOG_REDELIVER_REMARKS)
            df_bl['dispatch_plan'] = df_bl['destination_site_name']
            df_bl.loc[is_redeliver, 'dispatch_plan'] = df_bl.loc[is_redeliver, 'take_site_name']
        else:
            df_bl['dispatch_plan'] = df_bl.get('destination_site_name', '')

        df_bl.rename(columns={
            'billcode':       'waybillNo',
            'take_site_name': 'pickNetworkName',
        }, inplace=True)

        fc_set = set(df_fc['waybillNo'].tolist()) if not df_fc.empty else set()
        df_bl = df_bl[~df_bl['waybillNo'].isin(fc_set)]
        df_bl.drop_duplicates(subset='waybillNo', keep='last', inplace=True)

        df_bl['data_source']         = 'Backlog'
        df_bl['status_order']        = 'Đang trên bãi'
        df_bl['next_station']        = df_bl['dispatch_plan'].map(d_buucuc).fillna('')
        df_bl['dispatchNetworkTime'] = ''
        df_bl['updateTime']          = ''
        df_bl['Pickup_time']         = ''

    print(f"   Backlog (sau lọc): {len(df_bl)}")

    if not df_dp_lookup.empty:
        fc_set = set(df_fc['waybillNo'].tolist()) if not df_fc.empty else set()
        df_dp_only = df_dp_lookup[~df_dp_lookup['waybillNo'].isin(fc_set)].copy()
    else:
        df_dp_only = pd.DataFrame()

    # ================================================================
    # UNION
    # ================================================================
    frames = [f for f in [df_fc, df_dp_only, df_bl] if not f.empty]
    df_all = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df_all.empty:
        print("\n⚠️ Không có dữ liệu.")
        return

    if 'weight' in df_all.columns:
        df_all['weight'] = pd.to_numeric(df_all['weight'], errors='coerce').fillna(0.0).astype(float)
    else:
        df_all['weight'] = 0.0

    df_all['waybillNo'] = df_all['waybillNo'].astype(str).str.strip()
    print(f"   UNION total: {len(df_all)} đơn")

    # ================================================================
    # BỔ SUNG DATA TỪ DISPATCH LOOKUP
    # ================================================================
    if 'Pickup_time' not in df_all.columns:
        df_all['Pickup_time'] = ''

    if not df_dp_lookup.empty:
        dp_fill = df_dp_lookup[['waybillNo', 'dispatchNetworkTime', 'updateTime', 'status_order']].copy()
        dp_fill.columns = ['waybillNo', '_disp_time', '_upd_time', '_dp_status']

        df_all = df_all.merge(dp_fill, on='waybillNo', how='left')

        is_forecast_fail = (df_all['data_source'] == 'Forecast') & (df_all['_dp_status'] == 'Lấy hàng thất bại')
        df_all.loc[is_forecast_fail, '_dp_status'] = 'Đã điều phối nhân viên'

        df_all['dispatchNetworkTime'] = df_all['dispatchNetworkTime'].fillna('')
        df_all['dispatchNetworkTime'] = df_all['_disp_time'].where(
            df_all['_disp_time'].notna() & (df_all['_disp_time'].astype(str).str.strip() != ''),
            df_all['dispatchNetworkTime']
        )

        # Preserve forecast delivery time (Pickup_time) and actual pickup time (updateTime) separately
        df_all['updateTime'] = df_all['_upd_time'].fillna('')

        has_status = df_all['status_order'].notna() & (df_all['status_order'].astype(str).str.strip() != '')
        df_all['status_order'] = df_all['status_order'].where(has_status, df_all['_dp_status'])

        df_all.drop(columns=['_disp_time', '_upd_time', '_dp_status'], inplace=True)
    else:
        df_all['updateTime'] = df_all.get('updateTime', '').fillna('').astype(str)
        df_all['updateTime'] = df_all['updateTime'].where(
            df_all['updateTime'].str.strip() != '',
            df_all['Pickup_time'].fillna('')
        )

    # ================================================================
    # INBOUND / OUTBOUND
    # ================================================================
    df_in = pd.DataFrame(results.get('inbound', []))
    if not df_in.empty:
        df_in['scanDate'] = pd.to_datetime(df_in['scanDate'], errors='coerce')
        df_in = df_in.sort_values('scanDate').groupby('billNo', as_index=False).last()[['billNo', 'scanDate', 'sendSite']]
        df_in.rename(columns={'scanDate': 'inbound_scanDate', 'sendSite': 'inbound_network'}, inplace=True)

    df_out = pd.DataFrame(results.get('outbound', []))
    if not df_out.empty:
        df_out['scanDate'] = pd.to_datetime(df_out['scanDate'], errors='coerce')
        df_out = df_out.sort_values('scanDate').groupby('billNo', as_index=False).last()[['billNo', 'scanDate', 'upOrNextStation']]
        df_out.rename(columns={'scanDate': 'outbound_scanDate', 'upOrNextStation': 'dispatch_actual'}, inplace=True)

    df = df_all.copy()
    if not df_in.empty:
        df = df.merge(df_in,  left_on='waybillNo', right_on='billNo', how='left').drop(columns=['billNo'], errors='ignore')
    if not df_out.empty:
        df = df.merge(df_out, left_on='waybillNo', right_on='billNo', how='left').drop(columns=['billNo'], errors='ignore')

    # Exclude Forecast rows that were already Outbound in a previous operating ca (outbound scan date before 6:00 AM of today, or operating date of outbound is prior to today)
    if 'outbound_scanDate' in df.columns:
        def is_prior_outbound(row):
            if row.get('data_source') != 'Forecast':
                return False
            out_val = row.get('outbound_scanDate')
            if not out_val or pd.isna(out_val) or str(out_val).strip() in ('', 'nan', 'None'):
                return False
            try:
                # Parse outbound scan date and get its operating date
                dt_out = pd.to_datetime(out_val)
                op_date_out = get_operating_date(dt_out)
                
                # Get the row's operating date from forecast reference time
                t_ref = row.get('time_ref')
                if t_ref:
                    op_date_row = get_operating_date(t_ref)
                else:
                    op_date_row = get_operating_date(now)
                
                # If outbound happened in a prior operating date, exclude it
                return op_date_out < op_date_row
            except Exception:
                return False

        is_prior = df.apply(is_prior_outbound, axis=1)
        print(f"   ℹ| Loại bỏ {is_prior.sum()} đơn Forecast đã Outbound từ ca vận hành trước.")
        df = df[~is_prior].copy()

    if 'inbound_scanDate' in df.columns:
        is_backlog_empty_pick = (
            (df['data_source'] == 'Backlog') &
            (df['Pickup_time'].isna() | (df['Pickup_time'].astype(str).str.strip() == ''))
        )
        df.loc[is_backlog_empty_pick, 'Pickup_time'] = (
            df.loc[is_backlog_empty_pick, 'inbound_scanDate'].astype(str).str.strip()
        )

    # ── pickup_label & Pickup_ontime ──
    def assign_pickup_labels(row):
        disp = str(row.get('dispatchNetworkTime', '')).strip()
        pick = str(row.get('Pickup_time', '')).strip()
        if not disp or disp == 'nan' or not pick or pick == 'nan':
            return '', ''
        try:
            d_disp = disp[:10]
            d_pick = pick[:10]
            if d_disp == d_pick:
                return 'Lấy trong ngày', 'YES'
            elif d_disp < d_pick:
                return 'Lấy ngày hôm sau', 'NO'
            else:
                return '', 'NO'
        except Exception:
            return '', ''

    df[['pickup_label', 'Pickup_ontime']] = df.apply(
        assign_pickup_labels, axis=1, result_type='expand'
    )

    # ── build_status ──
    def has_value(val):
        return pd.notna(val) and str(val).strip() not in ('', 'nan', 'None')

    def build_status(row):
        # 1. Đã rời HUB
        if has_value(row.get('outbound_scanDate')):
            return 'Đã rời HUB'

        # 2. Đang trên bãi (Đã quét nhập kho HUB)
        if has_value(row.get('inbound_scanDate')):
            return 'Đang trên bãi'

        # 3. Đã lấy hàng (Gộp Đã lấy hàng và các đơn chưa về HUB thuộc Forecast/Dispatch thô)
        if has_value(row.get('Pickup_time')) or row.get('data_source') == 'Forecast':
            return 'Đã lấy hàng'

        # 4. Đã điều phối bưu cục (Mức ưu tiên thấp nhất)
        return 'Đã điều phối bưu cục'

    df['status_order'] = df.apply(build_status, axis=1)

    df['Tuyến'] = df['next_station'].map(d_tuyen).fillna('')
    df['Rank']  = df['next_station'].map(d_rank).fillna('')

    col_order = [
        'waybillNo', 'data_source', 'weight',
        'pickNetworkName', 'dispatch_plan',
        'Pickup_time', 'pickup_label', 'Pickup_ontime',
        'dispatchNetworkTime',
        'next_station', 'Tuyến', 'Rank',
        'inbound_network', 'inbound_scanDate',
        'outbound_scanDate', 'dispatch_actual',
        'status_order'
    ]
    df = df[[c for c in col_order if c in df.columns]]

    # Khởi tạo SQLite DB và UPSERT dữ liệu thô
    init_db()
    
    print("\n💾 Đang lưu dữ liệu thô vào SQLite Database cục bộ...")
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # ⚡ TỐI ƯU HÓA HIỆU NĂNG GHI CỰC ĐẠI
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA synchronous = OFF")
        c.execute("PRAGMA cache_size = -64000")
        c.execute("PRAGMA temp_store = MEMORY")
        
        # Chuẩn bị dữ liệu để UPSERT
        # Đảm bảo time_ref có giá trị để tính operating date
        if 'time_ref' not in df.columns:
            df['time_ref'] = df.get('Pickup_time', '')
            
        columns_to_db = [
            'waybillNo', 'data_source', 'weight', 'pickNetworkName', 'dispatch_plan',
            'Pickup_time', 'pickup_label', 'Pickup_ontime', 'dispatchNetworkTime',
            'next_station', 'Tuyến', 'Rank', 'inbound_network', 'inbound_scanDate',
            'outbound_scanDate', 'dispatch_actual', 'status_order', 'time_ref'
        ]
        
        # Đảm bảo đầy đủ cột trong DataFrame
        for col in columns_to_db:
            if col not in df.columns:
                df[col] = ''
                
        db_df = df[columns_to_db].copy()
        
        # Convert nan/None to empty string
        for col in columns_to_db:
            db_df[col] = db_df[col].fillna('').astype(str).str.strip()
            
        # Parse weight to float
        db_df['weight'] = pd.to_numeric(db_df['weight'], errors='coerce').fillna(0.0).astype(float)
        
        # Thực hiện UPSERT (Nếu trùng waybillNo thì REPLACE để cập nhật trạng thái mới nhất)
        records = db_df.values.tolist()
        c.executemany("""
            INSERT OR REPLACE INTO inventory (
                waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                outbound_scanDate, dispatch_actual, status_order, time_ref,
                last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, records)
        
        conn.commit()
        print(f"   ✅ Đã UPSERT thành công {len(records)} đơn vào SQLite state store.")
        conn.close()
    except Exception as ex_db:
        print(f"   ❌ Lỗi lưu dữ liệu vào SQLite state store: {ex_db}")
    
    # ── Tính toán sản lượng Outbound thực tế để ghi Sheets ──
    outbound_volumes_grouped = {}
    target_dates = set()
    
    if run_outbound:
        print("\n📊 Bắt đầu tính toán sản lượng Outbound theo ca vận hành...")
        raw_out_data = results.get('outbound', [])
        if raw_out_data:
            df_out_raw = pd.DataFrame(raw_out_data)
            if not df_out_raw.empty:
                for c in ['billNo', 'upOrNextStation', 'scanDate']:
                    if c not in df_out_raw.columns:
                        df_out_raw[c] = ''
                    else:
                        df_out_raw[c] = df_out_raw[c].fillna('').astype(str).str.strip()

                df_out_raw['scanDate_dt'] = pd.to_datetime(df_out_raw['scanDate'], errors='coerce')
                df_out_raw = df_out_raw.dropna(subset=['scanDate_dt'])
                
                # Map operating date (06:00 -> 06:00)
                df_out_raw['operating_date'] = df_out_raw['scanDate_dt'].apply(
                    lambda dt: dt.strftime('%Y-%m-%d') if dt.hour >= 6 else (dt - timedelta(days=1)).strftime('%Y-%m-%d')
                )
                
                # Deduplicate: keep last scan per billNo per operating_date
                df_out_raw = df_out_raw.sort_values('scanDate_dt')
                df_out_raw = df_out_raw.drop_duplicates(subset=['billNo', 'operating_date'], keep='last')
                
                df_out_raw['next_station'] = df_out_raw['upOrNextStation'].map(d_buucuc).fillna('')
                df_out_raw['next_station_clean'] = df_out_raw['next_station'].astype(str).str.strip().str.upper()
                df_out_raw = df_out_raw[df_out_raw['next_station_clean'] != '']
                
                # Direct parse JFS weight from outbound dynamic report scans
                if 'weight' in df_out_raw.columns:
                    df_out_raw['weight'] = pd.to_numeric(df_out_raw['weight'], errors='coerce').fillna(0.0).astype(float)
                else:
                    df_out_raw['weight'] = 0.0
                
                outbound_volumes_grouped = df_out_raw.groupby(['operating_date', 'next_station_clean']).agg(
                    volume=('billNo', 'size'),
                    weight=('weight', 'sum')
                ).to_dict(orient='index')
                target_dates = set(df_out_raw['operating_date'].unique())
                total_vol = sum(item['volume'] for item in outbound_volumes_grouped.values())
                print(f"   💡 Outbound calculated: {len(outbound_volumes_grouped)} groups. Total: {total_vol}")

    # Cập nhật dữ liệu lên Google Sheets
    update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, now.strftime('%Y-%m-%d'), results, d_buucuc)


def main():
    parser = argparse.ArgumentParser(description="J&T Cargo HCM HUB Inventory & Outbound Sync")
    parser.add_argument("--rebuild", type=int, help="Rebuild data for the last N operating days (bypasses hour check)")
    args = parser.parse_args()

    session = build_session()
    token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)
    try:
        run_once(session, token_mgr, rebuild_days=args.rebuild)
    except Exception as e:
        print(f"\n❌ Lỗi thực thi: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
