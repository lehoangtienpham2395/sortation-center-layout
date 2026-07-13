import os
import re
import io
import sys
import json
import time
import math
import gzip
import base64
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

# —— Windows Unicode Fix (cần cho GitHub Actions chạy trên Ubuntu, giữ để đồng nhất) ——
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# ============================================================
# CONFIG ĐĂNG NHẬP (Đọc từ GitHub Secrets / Environment Variables)
ACCOUNT    = os.environ.get("SYSTEM_ACCOUNT", "").strip() or "660021"
PASSWORD   = os.environ.get("SYSTEM_PASSWORD", "").strip() or "Tien@giang2395"
COUNTRY_ID = "1"
LOGIN_URL  = "https://gw.jtcargo.com.vn/basicdata/login"

# Google Sheet ID
SHEET_ID = "1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI"
DISABLE_GOOGLE_SHEETS = True

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
URL_BACKLOG        = URL_SCAN
URL_DISPATCH       = 'https://gw.jtcargo.com.vn/customerplatform/omsOrderDispatch/page'

# New correct operating platform endpoints for Linehaul, Arrival & Departure
URL_LINEHAUL       = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryTraceSubForPage'
URL_UNLOADING      = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryOpsUnloadingSchedulForPage'
URL_LOADING        = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryOpsLoadingSchedulForPage'


# ============================================================
# TUNING — đã tối ưu để tăng tốc ~5x so với mặc định
# ============================================================
SOURCE_WORKERS      = 4   # ⚡ Tối ưu lại để tránh bị JFS chặn/429/502 khi chạy từ GitHub Actions
PAGE_WORKERS        = 4   # ⚡ Giảm concurrency tránh quá tải JFS API
POOL_SIZE           = 32  # ⚡ Tương thích với số lượng worker nhỏ hơn
REQUEST_TIMEOUT     = 60
MAX_RETRIES         = 5
BACKOFF_BASE        = 3
INTER_REQUEST_DELAY = 0

# ============================================================
# GITHUB DATA PUSH CONFIG
# ============================================================
GH_REPO      = os.environ.get("GH_REPO", "lehoangtienpham2395/sortation-center-layout")
GH_TOKEN     = os.environ.get("GITHUB_TOKEN", "").strip()
GH_DATA_PATH = "data/latest.json.gz"  # Path trong repo để lưu data

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
        self.network_id = None  # ✅ Lưu trữ networkId của tài khoản
        self._lock = threading.Lock()

    def _login(self) -> str:
        if not self.account or not self.password:
            raise ValueError("SYSTEM_ACCOUNT and SYSTEM_PASSWORD environment variables must be defined!")
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
                # ✅ Lấy networkId động của user (HQ: 22, HCM Hub: 11888,...)
                if isinstance(data, dict) and data.get('networkId'):
                    self.network_id = data.get('networkId')
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


def calculate_shipment_status(forecast_time, pickup_time, arrival_time, inbound_time, outbound_time):
    # Normalize inputs
    def clean_val(val):
        if val is None:
            return ""
        s = str(val).strip()
        if s.lower() in ('nan', 'none', 'n/a', 'null', 'nat', ''):
            return ""
        return s

    ft = clean_val(forecast_time)
    pt = clean_val(pickup_time)
    at = clean_val(arrival_time)
    it = clean_val(inbound_time)
    ot = clean_val(outbound_time)

    # 1. Outbound (Đã rời HUB)
    if ot:
        return "Đã rời HUB", 0
    # 2. Inbound (Đang trên bãi)
    if it:
        return "Đang trên bãi", 0
    # 3. Transporting (Đang trên đường)
    if at:
        return "Đang trên đường", 1
    # 4. Pickup Done (Đã lấy hàng)
    if pt:
        return "Đã lấy hàng", 1
    # 5. Created (Đã điều phối bưu cục)
    if ft:
        return "Đã điều phối bưu cục", 1
    
    return "Đã điều phối bưu cục", 1


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
    
    # 1. Tạo bảng shipments mới
    c.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
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
            Arrival_time TEXT,
            dispatch_actual TEXT,
            status_order TEXT,
            time_ref TEXT,
            is_backlog INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_time_ref ON shipments(time_ref)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_status ON shipments(status_order)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_active ON shipments(is_active)")
    
    # 2. Kiểm tra nếu bảng inventory cũ tồn tại thì migrate sang shipments
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory'")
    if c.fetchone():
        print("   📦 Phát hiện bảng 'inventory' cũ. Bắt đầu migrate sang bảng 'shipments'...")
        try:
            # Kiểm tra xem cột Arrival_time có tồn tại trong inventory không, tự động thêm nếu chưa có
            try:
                c.execute("ALTER TABLE inventory ADD COLUMN Arrival_time TEXT")
            except Exception:
                pass
                
            c.execute("""
                INSERT OR IGNORE INTO shipments (
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    is_backlog, is_active, last_updated
                )
                SELECT 
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    CASE WHEN inbound_scanDate = 'Backlog' THEN 1 ELSE 0 END,
                    CASE WHEN (inbound_scanDate IS NULL OR inbound_scanDate = '' OR inbound_scanDate = 'Backlog') 
                          AND (outbound_scanDate IS NULL OR outbound_scanDate = '') THEN 1 ELSE 0 END,
                    last_updated
                FROM inventory
            """)
            conn.commit()
            print("   ✅ Migrate dữ liệu thành công!")
            # Drop bảng cũ
            c.execute("DROP TABLE inventory")
            conn.commit()
            print("   🗑️ Đã xóa bảng 'inventory' cũ.")
        except Exception as e_migrate:
            print(f"   ⚠️ Lỗi migrate dữ liệu: {e_migrate}")
            
    # Tự động dọn dẹp các bản ghi ĐÃ RỜI HUB / Inbound (không active) cũ hơn 7 ngày để tối ưu hóa DB
    try:
        limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("""
            DELETE FROM shipments 
            WHERE is_active = 0 
              AND datetime(last_updated) < datetime(?)
        """, (limit_date,))
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


def auth_get(session, url, token_mgr, base_headers, params=None, label=''):
    """
    Authenticated GET request với retry + token refresh.
    Dùng cho URL_SELECT khi cần lookup thông tin trạm.
    """
    last_exc  = None
    refreshed = False
    attempt   = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        token   = token_mgr.get_token()
        headers = dict(base_headers)
        # ✅ JFS API GET endpoints yêu cầu cả Authtoken (PascalCase) và authToken (camelCase) tùy thuộc gateway routing
        headers['Authtoken'] = token
        headers['authToken'] = token
        try:
            r = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            wait = BACKOFF_BASE * attempt
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
    """
    Tìm mã code, ID và TypeID của bưu cục dựa trên tên.
    API basicdata/network/select yêu cầu xác thực bằng cả token và dcr_key.
    """
    URL_SELECT = 'https://gw.jtcargo.com.vn/basicdata/network/select'
    parts = station_name.strip().split(' ', 1)
    search_name = parts[1] if len(parts) > 1 else station_name
    
    # ✅ Dùng networkId động của tài khoản đang đăng nhập (HQ/toàn quốc là 22, HCM Hub là 11888)
    # Nếu không tìm thấy, fallback về HCM Hub (11888)
    net_id = str(token_mgr.network_id) if (hasattr(token_mgr, 'network_id') and token_mgr.network_id) else "11888"
    
    params = {
        "dcr_key": "57b048fb-bc8c-4d24-982b-a750b7ce8693",
        "name": search_name,
        "networkId": net_id,
        "queryLevel": "3",
        "current": 1,
        "size": 20
    }
    try:
        r = auth_get(session, URL_SELECT, token_mgr, headers, params=params, label=f'Select {search_name}')
        res = r.json()
        if res.get('succ') or res.get('code') == 1:
            records = res.get('data', {}).get('records', [])
            for rec in records:
                rec_name = rec.get('name', '').upper()
                if station_name.upper() in rec_name or search_name.upper() in rec_name:
                    return {
                        "code":   rec.get('code') or rec.get('networkCode'),
                        "id":     rec.get('id'),
                        "name":   rec.get('name'),
                        "typeId": rec.get('typeId') or rec.get('networkTypeId')
                    }
    except Exception as e:
        print(f"      ⚠️ Lỗi lấy thông tin trạm {station_name}: {e}")
    return None


def upsert_arrival(df_old: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    """
    Upsert dữ liệu Arrival theo key (Ngày vận hành, Pickup_station, Scan Hour).
    Dữ liệu cùng key → ghi đè bằng mới nhất. Ngày cũ không có trong đợt này → giữ nguyên.
    """
    key_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour']
    if df_old.empty:
        return df_new
    for col in key_cols:
        if col in df_old.columns:
            df_old[col] = df_old[col].astype(str).str.strip()
        if col in df_new.columns:
            df_new[col] = df_new[col].astype(str).str.strip()
    df_old['_key'] = df_old[key_cols].agg('|'.join, axis=1)
    df_new['_key'] = df_new[key_cols].agg('|'.join, axis=1)
    new_keys   = set(df_new['_key'])
    df_keep    = df_old[~df_old['_key'].isin(new_keys)].drop(columns=['_key'])
    df_new     = df_new.drop(columns=['_key'])
    result     = pd.concat([df_keep, df_new], ignore_index=True)
    result     = result.sort_values(by=key_cols, ascending=[False, True, True])
    return result


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
    # 1. Đọc danh sách bưu cục Miền Nam (HCM/SE) + BN HUB từ stations_master.csv
    station_names = []
    # Ưu tiên load từ config của repo trước (để chạy được trên GitHub Actions)
    repo_master_path = os.path.join(BASE_DIR, "config", "stations_master.csv")
    master_path = repo_master_path if os.path.exists(repo_master_path) else r"C:\Users\lehoa\OneDrive\Desktop\testing\stations_master.csv"
    
    if os.path.exists(master_path):
        try:
            df_m = pd.read_csv(master_path)
            # Lấy các trạm thuộc HCM và SE (Đông Nam) và bổ sung BN HUB
            df_filtered = df_m[
                df_m['master_area'].str.contains('HCM|SE', na=False, case=False) |
                df_m['station_name'].str.contains('BN HUB', na=False, case=False)
            ].copy()
            station_names = df_filtered['station_name'].dropna().unique().tolist()
            print(f"   📂 Load thành công {len(station_names)} bưu cục (bao gồm BN HUB) từ: {master_path}")
        except Exception as e_sm:
            print(f"   ⚠️ Lỗi đọc stations_master.csv ({master_path}): {e_sm}")
            
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
    df['scantime_dt'] = pd.to_datetime(df.get('scantime'), errors='coerce')
    df['Ngày vận hành'] = (df['scantime_dt'] - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
    df['Scan Hour']     = df['scantime_dt'].dt.hour.fillna(-1).astype(int)

    # Logic đặc biệt cho BN HUB:
    # 1. Ngày vận hành = Ngày xuất phát gốc + 36 tiếng (chu kỳ Bắc-Nam thực tế).
    #    Lấy trực tiếp ngày dương lịch cập bến làm Ngày vận hành (không trừ 6h cycle vận hành của bưu cục).
    # 2. Scan Hour giữ nguyên giờ quét gốc của bưu cục phát.
    found_scansite_col = None
    for col in df.columns:
        if col.lower() == 'scansitename':
            found_scansite_col = col
            break
            
    if found_scansite_col:
        df = df.rename(columns={found_scansite_col: 'Pickup_station'})
        is_bn_hub = df['Pickup_station'].astype(str).str.strip().str.upper() == 'BN HUB'
        if is_bn_hub.any():
            # Ngày vận hành mới = Ngày xuất phát gốc + 36 tiếng
            df.loc[is_bn_hub, 'Ngày vận hành'] = (df.loc[is_bn_hub, 'scantime_dt'] + pd.Timedelta(hours=36)).dt.strftime('%Y-%m-%d')
            # Scan Hour giữ nguyên giờ quét gốc
            df.loc[is_bn_hub, 'Scan Hour'] = df.loc[is_bn_hub, 'scantime_dt'].dt.hour.fillna(-1).astype(int)

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
        data_node = r.json().get('data', {})
        if isinstance(data_node, dict):
            return data_node.get('records', []) or []
        elif isinstance(data_node, list):
            return data_node
        return []

    # ⚡ Dùng parallel thay vì sequential khi đã biết total
    if total and total > page_size:
        all_data = pull_pages_parallel(fetch_page, total, page_size, label)
    else:
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

    # ⚡ Dùng parallel khi đã biết total để tăng tốc đáng kể
    if total is not None and total > page_size:
        all_data = pull_pages_parallel(fetch_page, total, page_size, label)
    else:
        all_data = pull_pages_sequential(fetch_page, page_size, label, total=total, stop_short=True)

    if total is not None and len(all_data) < total:
        print(f"   ⚠️ {label}: thu {len(all_data)} < tổng {total} (có thể có trang lỗi)")
    print(f"   ✅ {label}: {len(all_data)}/{total if total is not None else '?'} dòng")
    return all_data


def pull_dispatch(session, token_mgr, headers, base_payload, label='Dispatch'):
    page_size = int(base_payload.get('size', 1000))

    def fetch_page(p):
        payload = {**base_payload, 'current': p}
        url = URL_DISPATCH
        r = auth_post(session, url, token_mgr, headers, data=payload, label=label)
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
# GITHUB DATA PUSH — Bypass Google Sheet bottleneck với 100k rows
# ================================================================
def push_json_to_github(df: pd.DataFrame, token: str, repo_name: str, path: str = GH_DATA_PATH) -> bool:
    """
    Push DataFrame dưới dạng gzip JSON lên Github raw.
    Dashboard JS sẽ đọc trực tiếp từ raw.githubusercontent.com — không cần Sheet API.
    
    Returns:
        True nếu push thành công, False nếu không có token hoặc lỗi.
    """
    if not token:
        print("   ⚠️ GITHUB_TOKEN không được set — bỏ qua push JSON lên Github.")
        return False

    try:
        print(f"   📦 Đang nén {len(df):,} dòng → gzip JSON...")
        t0 = time.time()

        # Serialize + compress: 100k rows ~20MB → ~2-4MB
        payload_str = df.to_json(orient="records", force_ascii=False, date_format="iso")
        compressed  = gzip.compress(payload_str.encode("utf-8"), compresslevel=6)
        encoded     = base64.b64encode(compressed).decode()
        size_kb     = len(compressed) / 1024

        print(f"   📦 Nén xong: {size_kb:.0f} KB (mất {time.time()-t0:.1f}s) — đang push lên Github...")

        # Gọi Github API
        api_url  = f"https://api.github.com/repos/{repo_name}/contents/{path}"
        headers  = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        commit_msg = f"data: sync {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%H:%M %d/%m/%Y')}"

        # Kiểm tra file cũ để lấy SHA (cần cho update)
        sha = None
        r_get = requests.get(api_url, headers=headers, timeout=30)
        if r_get.status_code == 200:
            sha = r_get.json().get("sha")

        body = {"message": commit_msg, "content": encoded}
        if sha:
            body["sha"] = sha

        r_put = requests.put(api_url, headers=headers, json=body, timeout=60)
        r_put.raise_for_status()

        action = "Cập nhật" if sha else "Tạo mới"
        print(f"   ✅ {action} thành công: {path} ({size_kb:.0f} KB, {len(df):,} rows) | tổng {time.time()-t0:.1f}s")
        return True

    except Exception as e:
        print(f"   ❌ Lỗi push JSON lên Github: {e}")
        return False


def push_db_to_github(db_path: str, token: str, repo_name: str, github_path: str = "backend_sync/db/state.db") -> bool:
    """
    Push trực tiếp file cơ sở dữ liệu SQLite (state.db) lên Github repository.
    Giúp bảo toàn 100% dữ liệu lịch sử mốc giờ lấy hàng và tránh việc Github Actions
    làm mất/reset dữ liệu.
    """
    if not token:
        print("   ⚠️ GITHUB_TOKEN không được set — bỏ qua đồng bộ DB lên Github.")
        return False
    if not os.path.exists(db_path):
        print(f"   ⚠️ File DB không tồn tại tại {db_path}.")
        return False

    try:
        t0 = time.time()
        with open(db_path, "rb") as f:
            db_data = f.read()

        encoded = base64.b64encode(db_data).decode()
        size_mb = len(db_data) / (1024 * 1024)
        print(f"   💾 Đang tải DB lên Github: {github_path} ({size_mb:.2f} MB)...")

        api_url = f"https://api.github.com/repos/{repo_name}/contents/{github_path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        commit_msg = f"data: update state.db {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%H:%M %d/%m/%Y')}"

        sha = None
        r_get = requests.get(api_url, headers=headers, timeout=20)
        if r_get.status_code == 200:
            sha = r_get.json().get("sha")

        body = {"message": commit_msg, "content": encoded}
        if sha:
            body["sha"] = sha

        r_put = requests.put(api_url, headers=headers, json=body, timeout=120)
        r_put.raise_for_status()

        print(f"   ✅ Đồng bộ DB lên Github thành công ({size_mb:.2f} MB) | tổng {time.time()-t0:.1f}s")
        return True
    except Exception as e:
        print(f"   ❌ Lỗi đồng bộ DB lên Github: {e}")
        return False


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
def update_outbound_sheet(ss, master_chutes, outbound_volumes_grouped, target_dates):
    all_rows = []
    sheet = None
    
    # Read from sheet if not disabled
    if not DISABLE_GOOGLE_SHEETS and ss:
        try:
            sheet = ss.worksheet("Outbound")
            all_rows = sheet.get_all_values()
        except Exception:
            try:
                sheet = ss.add_worksheet("Outbound", rows=1000, cols=7)
            except Exception:
                sheet = None
                
    # Read from local json if empty
    if not all_rows:
        local_path = "data/outbound.json"
        if os.path.exists(local_path):
            try:
                df_old = pd.read_json(local_path)
                if not df_old.empty:
                    all_rows = [["Zone", "AreaID", "Bưu cục", "Volume", "Weight", "Sức chứa", "Ngày"]]
                    for _, r in df_old.iterrows():
                        all_rows.append([
                            str(r.get("Zone", "")), str(r.get("AreaID", "")), str(r.get("Bu cc", "")),
                            int(r.get("Volume", 0)), int(r.get("Weight", 0)), str(r.get("Sc cha", "780")),
                            str(r.get("Ngy", ""))
                        ])
            except Exception:
                pass
                
    headers = ["Zone", "AreaID", "Bưu cục", "Volume", "Weight", "Sức chứa", "Ngày"]
    new_rows = [headers]
    if all_rows:
        for r in all_rows[1:]:
            while len(r) < len(headers):
                r.append("")
            try:
                zone = r[0]
                area_id = r[1]
                name = r[2]
                vol = int(str(r[3]).replace(".", "").replace(",", ""))
                weight = int(str(r[4]).replace(".", "").replace(",", ""))
                capacity = r[5]
                date = r[6].strip()
                
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
            
    # Write to local JSON
    os.makedirs("data", exist_ok=True)
    df_outbound = pd.DataFrame(new_rows[1:], columns=["Zone", "AreaID", "Bu cc", "Volume", "Weight", "Sc cha", "Ngy"])
    df_outbound.to_json("data/outbound.json", orient="records", force_ascii=False)
    print(f"   💾 Đã lưu file 'data/outbound.json' với {len(new_rows)-1} dòng.")

    # Write to Google Sheet if not disabled
    if not DISABLE_GOOGLE_SHEETS and sheet:
        try:
            sheet.clear()
            sheet.update(range_name="A1", values=new_rows)
            print(f"   ✅ Đã cập nhật sheet 'Outbound' cho các ngày: {list(target_dates)}")
        except Exception as e:
            print(f"   ⚠️ Lỗi ghi sheet Outbound: {e}")


def update_backlog_sheet(ss, master_chutes, backlog_volumes, current_date_str):
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
        
    # Write to local JSON
    os.makedirs("data", exist_ok=True)
    df_backlog = pd.DataFrame(new_rows[1:], columns=["Zone", "AreaID", "Bu cc", "Volume", "Weight", "Sc cha", "Ngy"])
    df_backlog.to_json("data/backlog.json", orient="records", force_ascii=False)
    print(f"   💾 Đã lưu file 'data/backlog.json' với {len(new_rows)-1} dòng.")

    # Write to Google Sheet if not disabled
    if not DISABLE_GOOGLE_SHEETS and ss:
        try:
            try:
                sheet = ss.worksheet("Backlog")
            except Exception:
                sheet = ss.add_worksheet("Backlog", rows=1000, cols=7)
            sheet.clear()
            sheet.update(range_name="A1", values=new_rows)
            print(f"   ✅ Đã cập nhật sheet 'Backlog' pivoted với {len(new_rows)-1} dòng.")
        except Exception as e:
            print(f"   ⚠️ Lỗi ghi sheet Backlog: {e}")


def update_inventory_sheet(ss, master_chutes, inventory_volumes, current_date_str):
    headers = ["Zone", "AreaID", "Bưu cục", "Trạng thái", "Volume", "Weight", "Sức chứa", "Ngày"]
    statuses = ['Đang trên bãi', 'Đang trên đường', 'Đã lấy hàng', 'Đã điều phối bưu cục', 'Đã rời HUB']
    
    # Count occurrences of each station name to distribute volume/weight and avoid double-counting
    station_counts = {}
    for (zone, area_id), info in master_chutes.items():
        name_upper = info["name"].strip().upper()
        station_counts[name_upper] = station_counts.get(name_upper, 0) + 1
        
    station_seen_counts = {}
    new_rows = [headers]
    for (zone, area_id), info in master_chutes.items():
        name_upper = info["name"].strip().upper()
        chutes_cnt = station_counts.get(name_upper, 1)
        chute_idx = station_seen_counts.get(name_upper, 0)
        station_seen_counts[name_upper] = chute_idx + 1
        
        for status in statuses:
            info_vol_wt = inventory_volumes.get((name_upper, status), {'volume': 0, 'weight': 0})
            total_vol = int(info_vol_wt['volume'])
            
            # Integer distribution for Volume
            vol_base = total_vol // chutes_cnt
            vol_rem = total_vol % chutes_cnt
            vol = vol_base + (1 if chute_idx < vol_rem else 0)
            
            weight = round(info_vol_wt['weight'] / chutes_cnt, 2)
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
            
    # Write to local JSON
    os.makedirs("data", exist_ok=True)
    df_inventory = pd.DataFrame(new_rows[1:], columns=["Zone", "AreaID", "Bu cc", "Trng thi", "Volume", "Weight", "Sc cha", "Ngy"])
    df_inventory.to_json("data/inventory.json", orient="records", force_ascii=False)
    print(f"   💾 Đã lưu file 'data/inventory.json' với {len(new_rows)-1} dòng.")

    # Write to Google Sheet if authorized
    if ss:
        try:
            try:
                sheet = ss.worksheet("Inventory")
            except Exception:
                sheet = ss.add_worksheet("Inventory", rows=1000, cols=8)
            sheet.clear()
            sheet.update(range_name="A1", values=new_rows)
            print(f"   ✅ Đã cập nhật sheet 'Inventory' pivoted với {len(new_rows)-1} dòng lên Google Sheets.")
        except Exception as e:
            print(f"   ⚠️ Lỗi ghi sheet Inventory: {e}")


def update_inbound_sheets(ss, results, master_chutes, d_buucuc):
    print("\n📥 Bắt đầu cập nhật dữ liệu Inbound gom nhóm theo trạng thái & khùng giờ lên Google Sheets...")
    
    def safe_hour_format(val):
        if not val or str(val).strip().lower() in ('nan', 'none', 'nat', 'n/a', 'backlog', ''):
            return ""
        try:
            dt = pd.to_datetime(val)
            if pd.isna(dt):
                return ""
            return dt.strftime('%Y-%m-%d %H:00')
        except Exception:
            return ""
            
    def write_sheet(sheet_name, df_data, headers):
        if df_data.empty:
            df_clean = pd.DataFrame(columns=headers)
        else:
            for h in headers:
                if h not in df_data.columns:
                    df_data[h] = ""
            df_clean = df_data[headers].fillna("")
            
        # Write to local JSON
        os.makedirs("data", exist_ok=True)
        col_mappings = {
            "Bưu cục": "Bu cc", "Trạng thái": "Trng thi", "Volume": "Volume", "Weight": "Weight",
            "Ngày vận hành_Inbound": "Ngy vn hnh_Inbound", "Ngày vận hành_Forecast": "Ngy vn hnh_Forecast",
            "Ngày vận hành_Pickup": "Ngy vn hnh_Pickup", "Ngày vận hành_Arrival": "Ngy vn hnh_Arrival", "Inbound Hour": "Inbound Hour",
            "Forecast Time": "Forecast Time", "Pickup Time": "Pickup Time", "Arrival Time": "Arrival Time", "Loại rớt": "Loi rt" 
        }
        df_json = df_clean.copy()
        df_json.rename(columns={k: v for k, v in col_mappings.items() if k in df_json.columns}, inplace=True)
        
        df_json.to_json(f"data/{sheet_name.lower()}.json", orient="records", force_ascii=False)
        print(f"   💾 Đã lưu file 'data/{sheet_name.lower()}.json' với {len(df_clean)} dòng.")
        
        # Write to Google Sheet if not disabled
        if not DISABLE_GOOGLE_SHEETS and ss:
            try:
                try:
                    sheet = ss.worksheet(sheet_name)
                except Exception:
                    sheet = ss.add_worksheet(sheet_name, rows=1000, cols=len(headers))
                
                sheet.clear()
                rows = [headers] + df_clean.values.tolist()
                sheet.update(range_name='A1', values=rows)
                print(f"   ✅ Đã cập nhật Sheet '{sheet_name}' với {len(rows)-1} dòng.")
            except Exception as e:
                print(f"   ❌ Lỗi ghi dữ liệu lên sheet '{sheet_name}': {e}")
                raise e

    # 1. Generate Inbound aggregated data directly from SQLite shipments table
    df_inbound_aggregated = pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_FILE)
        df_ship = pd.read_sql_query("""
            SELECT pickNetworkName, status_order, weight, 
                   inbound_scanDate, dispatchNetworkTime, Pickup_time, Arrival_time
            FROM shipments
        """, conn)
        conn.close()
    except Exception as e_db:
        print(f"   ⚠️ Lỗi kết nối DB khi tạo Inbound Sheet: {e_db}")
        df_ship = pd.DataFrame()

    from zoneinfo import ZoneInfo
    now_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    current_op_date = get_operating_date(now_vn.strftime('%Y-%m-%d %H:%M:%S'))

    if not df_ship.empty:
        unique_rows = []
        for _, row in df_ship.iterrows():
            ib_time = str(row.get('inbound_scanDate') or '').strip()
            pk_time = str(row.get('Pickup_time') or '').strip()
            fc_time = str(row.get('dispatchNetworkTime') or '').strip()
            arr_time = str(row.get('Arrival_time') or '').strip()
            
            # Mapping Status directly to English for Inbound Sheet
            status_map = {
                'Đang trên bãi': 'Inbound',
                'Đang trên đường': 'Transporting',
                'Đã lấy hàng': 'Pickup Done',
                'Đã điều phối bưu cục': 'Created'
            }
            status = status_map.get(row.get('status_order'), 'Created')
            
            # Skip outbound shipments in Inbound Sheet
            if row.get('status_order') == 'Đã rời HUB':
                continue
                
            op_date_ib = get_operating_date(ib_time) if ib_time else ""
            fc_time_temp = fc_time if fc_time else pk_time
            op_date_fc = get_operating_date(fc_time_temp) if fc_time_temp else ""
            op_date_pk = get_operating_date(pk_time) if pk_time else ""
            op_date_arr = get_operating_date(arr_time) if arr_time else ""

            # Calculate Drop Type
            if op_date_fc:
                if op_date_pk:
                    loai_rot = "Rớt hôm nay" if op_date_fc == op_date_pk else "Rớt hôm trước"
                else:
                    loai_rot = "Rớt hôm trước" if op_date_fc < current_op_date else "Rớt hôm nay"
            else:
                loai_rot = "Rớt hôm nay"

            ib_hour = safe_hour_format(ib_time)
            fc_hour = safe_hour_format(fc_time_temp)
            pk_hour = safe_hour_format(pk_time)
            arr_hour = safe_hour_format(arr_time)

            unique_rows.append({
                'Bưu cục': row.get('pickNetworkName') or '',
                'Trạng thái': status,
                'weight': float(row.get('weight') or 0.0),
                'Ngày vận hành_Inbound': op_date_ib,
                'Ngày vận hành_Forecast': op_date_fc,
                'Ngày vận hành_Pickup': op_date_pk,
                'Ngày vận hành_Arrival': op_date_arr,
                'Inbound Hour': ib_hour,
                'Forecast Time': fc_hour,
                'Pickup Time': pk_hour,
                'Arrival Time': arr_hour,
                'Loại rớt': loai_rot
            })

        # Backlog Carryover Projection
        # Đơn rớt hôm trước (chưa pickup) được CHUYỂN sang ngày hôm nay — không cộng thêm (tránh double-count)
        projected_rows = []
        for r in unique_rows:
            is_carryover = False
            if r['Trạng thái'] != 'Inbound':
                was_picked_before_today = r['Ngày vận hành_Pickup'] and r['Ngày vận hành_Pickup'] < current_op_date
                if not was_picked_before_today:
                    if r['Ngày vận hành_Forecast'] and r['Ngày vận hành_Forecast'] < current_op_date:
                        # Đơn rớt: REPLACE ngày gốc bằng ngày hôm nay, không thêm dòng mới
                        dup = r.copy()
                        dup['Ngày vận hành_Forecast'] = current_op_date
                        dup['Loại rớt'] = 'Rớt hôm trước'
                        projected_rows.append(dup)
                        is_carryover = True
            if not is_carryover:
                projected_rows.append(r)

        # Grouping & Aggregation
        grouped = {}
        for r in projected_rows:
            key = (
                r['Bưu cục'], r['Trạng thái'],
                r['Ngày vận hành_Inbound'], r['Ngày vận hành_Forecast'], r['Ngày vận hành_Pickup'], r['Ngày vận hành_Arrival'],
                r['Inbound Hour'], r['Forecast Time'], r['Pickup Time'], r['Arrival Time'], r['Loại rớt']
            )
            if key not in grouped:
                grouped[key] = {'volume': 0, 'weight': 0.0}
            grouped[key]['volume'] += 1
            grouped[key]['weight'] += r['weight']
            
        final_rows = []
        for (fc_name, status, op_ib, op_fc, op_pk, op_arr, ib_hour, fc_hour, pk_hour, arr_hour, loai_rot), stats in grouped.items():
            final_rows.append({
                'Bưu cục': fc_name,
                'Trạng thái': status,
                'Volume': stats['volume'],
                'Weight': int(stats['weight']),
                'Ngày vận hành_Inbound': op_ib,
                'Ngày vận hành_Forecast': op_fc,
                'Ngày vận hành_Pickup': op_pk,
                'Ngày vận hành_Arrival': op_arr,
                'Inbound Hour': ib_hour,
                'Forecast Time': fc_hour,
                'Pickup Time': pk_hour,
                'Arrival Time': arr_hour,
                'Loại rớt': loai_rot
            })
        df_inbound_aggregated = pd.DataFrame(final_rows)

    write_sheet("Inbound", df_inbound_aggregated, [
        "Bưu cục", "Trạng thái", "Volume", "Weight",
        "Ngày vận hành_Inbound", "Ngày vận hành_Forecast", "Ngày vận hành_Pickup", "Ngày vận hành_Arrival",
        "Inbound Hour", "Forecast Time", "Pickup Time", "Arrival Time", "Loại rớt" 
    ])

    # 2. Linehaul processing (remains direct from results)
    df_lh_raw = pd.DataFrame(results.get('linehaul', []))
    df_lh = pd.DataFrame()
    if not df_lh_raw.empty:
        for col in ['traceCode', 'traceSubCode', 'sendTime', 'loadingEndTime', 'endNetworkName', 'startNetworkName', 'nextNetworkName', 'unloadingStartTime', 'unloadingEndTime', 'unloadingBillPiece', 'unloadingWeight', 'billPiece', 'totalBillPiece', 'loadBillPiece', 'weight', 'totalWeight', 'loadWeight']:
            if col not in df_lh_raw.columns:
                df_lh_raw[col] = None
        
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
        
        def get_next_network_val(row):
            end_net = str(row.get('endNetworkName') or '').strip()
            start_net = str(row.get('startNetworkName') or '').strip()
            next_net = str(row.get('nextNetworkName') or '').strip()
            is_dest_hcm = 'HCM' in end_net.upper() or 'SR0001' in end_net.upper() or 'HCM' in next_net.upper() or 'SR0001' in next_net.upper()
            if is_dest_hcm:
                return d_buucuc.get(start_net, start_net)
            return ''
            
        df_lh_raw['nextNetworkName_clean'] = df_lh_raw.apply(get_next_network_val, axis=1)

        def aggregate_lh(group):
            send_t = group['sendTime'].dropna().str.strip().replace('', None).dropna()
            send_val = send_t.iloc[0] if not send_t.empty else ''
            load_et = group['loadingEndTime'].dropna().str.strip().replace('', None).dropna()
            load_val = load_et.iloc[0] if not load_et.empty else ''
            ust = group['unloadingStartTime'].dropna().str.strip().replace('', None).dropna()
            ust_val = ust.iloc[0] if not ust.empty else ''
            uet = group['unloadingEndTime'].dropna().str.strip().replace('', None).dropna()
            uet_val = uet.iloc[0] if not uet.empty else ''
            fc_names = group['nextNetworkName_clean'].dropna().str.strip().replace('', None).dropna()
            fc_val = fc_names.iloc[0] if not fc_names.empty else ''
            
            b_piece = group['billPiece_clean'].max()
            wt = group['weight_clean'].max()
            un_piece = group['unloadingBillPiece_clean'].max()
            un_wt = group['unloadingWeight_clean'].max()
            
            dt_src = ust_val if (ust_val and ust_val.lower() not in ('nan', 'none')) else (uet_val if (uet_val and uet_val.lower() not in ('nan', 'none')) else (send_val if (send_val and send_val.lower() not in ('nan', 'none')) else load_val))
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

        df_lh = df_lh_raw.groupby('traceSubCode', as_index=False).apply(aggregate_lh)
        df_lh.rename(columns={'traceSubCode': 'Phiếu nhiệm vụ con'}, inplace=True)
        df_lh = df_lh[df_lh['nextNetworkName'].astype(str).str.strip() != '']

    write_sheet("Linehaul", df_lh, ["Phiếu nhiệm vụ", "Phiếu nhiệm vụ con", "sendTime", "loadingEndTime", "nextNetworkName", "unloadingStartTime", "unloadingEndTime", "unloadingBillPiece", "unloadingWeight", "billPiece", "weight", "Ngày vận hành"])

    # 3. Arrival sheet (processed from shipments in SQLite)
    print("\n📋 Xử lý sheet Arrival từ shipments...")
    df_arrival_aggregated = pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_FILE)
        df_arr_raw = pd.read_sql_query("""
            SELECT waybillNo, pickNetworkName AS Pickup_station, Arrival_time, inbound_scanDate
            FROM shipments
            WHERE Arrival_time IS NOT NULL AND Arrival_time != ''
        """, conn)
        conn.close()
    except Exception as e_arr_db:
        print(f"   ⚠️ Lỗi kết nối DB cho Arrival sheet: {e_arr_db}")
        df_arr_raw = pd.DataFrame()

    if not df_arr_raw.empty:
        df_arr_raw['Ngày vận hành'] = df_arr_raw['Arrival_time'].apply(get_operating_date)
        df_arr_raw['Scan Hour'] = pd.to_datetime(df_arr_raw['Arrival_time'], errors='coerce').dt.strftime('%Y-%m-%d %H:00')
        
        df_arr_raw['Đã đến Hub'] = df_arr_raw['inbound_scanDate'].apply(lambda d: 1 if d and str(d).strip().lower() not in ('nan', 'none', '') else 0)
        df_arr_raw['Chưa đến Hub'] = 1 - df_arr_raw['Đã đến Hub']
        
        try:
            df_arr_raw['scantime_dt'] = pd.to_datetime(df_arr_raw['Arrival_time'], errors='coerce')
            df_pivot = df_arr_raw.groupby(['Ngày vận hành', 'Pickup_station', 'Scan Hour']).agg(
                **{
                    'Tổng số đơn':  ('waybillNo', 'size'),
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
            arrival_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour',
                            'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub', 'Last time']
            df_old = pd.DataFrame()
            
            arrival_json_path = "data/arrival.json"
            if os.path.exists(arrival_json_path):
                try:
                    df_old = pd.read_json(arrival_json_path)
                    df_old.rename(columns={
                        'Ngy vn hnh': 'Ngày vận hành',
                        'Tng s n': 'Tổng số đơn'
                    }, inplace=True)
                except Exception:
                    pass
                    
            if df_old.empty and not DISABLE_GOOGLE_SHEETS and ss:
                try:
                    arr_sheet = ss.worksheet('Arrival')
                    old_vals = arr_sheet.get_all_values()
                    if len(old_vals) > 1:
                        df_old = pd.DataFrame(old_vals[1:], columns=old_vals[0])
                except Exception:
                    pass
                    
            if not df_old.empty:
                for col in ['Scan Hour', 'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub']:
                    if col in df_old.columns:
                        df_old[col] = pd.to_numeric(df_old[col], errors='coerce').fillna(0).astype(int)
                today_dates = set(df_pivot['Ngày vận hành'].unique())
                df_old = df_old[~df_old['Ngày vận hành'].isin(today_dates)]
                df_arrival_aggregated = pd.concat([df_old, df_pivot[arrival_cols]], ignore_index=True)
            else:
                df_arrival_aggregated = df_pivot[arrival_cols].copy()
                
            df_arrival_aggregated = df_arrival_aggregated.sort_values(
                by=['Ngày vận hành', 'Pickup_station', 'Scan Hour'],
                ascending=[False, True, True]
            )
            all_dates = sorted(df_arrival_aggregated['Ngày vận hành'].unique(), reverse=True)
            df_arrival_aggregated = df_arrival_aggregated[df_arrival_aggregated['Ngày vận hành'].isin(all_dates[:7])]
            
            os.makedirs("data", exist_ok=True)
            df_final_json = df_arrival_aggregated.copy()
            df_final_json.rename(columns={
                'Ngày vận hành': 'Ngy vn hnh',
                'Tổng số đơn': 'Tng s n'
            }, inplace=True)
            df_final_json.to_json("data/arrival.json", orient="records", force_ascii=False)
            print(f"   💾 Đã lưu file 'data/arrival.json' với {len(df_arrival_aggregated)} dòng.")
            
            if not DISABLE_GOOGLE_SHEETS and ss:
                try:
                    try:
                        arr_sheet = ss.worksheet('Arrival')
                    except Exception:
                        arr_sheet = ss.add_worksheet('Arrival', rows=5000, cols=len(arrival_cols))
                    rows_to_write = [arrival_cols] + df_arrival_aggregated[arrival_cols].fillna('').values.tolist()
                    arr_sheet.clear()
                    arr_sheet.update(range_name='A1', values=rows_to_write)
                    print(f'   ✅ Sheet Arrival: {len(rows_to_write)-1} dòng (lịch sử 7 ngày).')
                except Exception as e_write:
                    print(f'   ❌ Lỗi ghi sheet Arrival: {e_write}')


def update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, current_date_str, results=None, d_buucuc=None, session=None, token_mgr=None, fh=None, fp=None):
    print(f"\n📊 Bắt đầu cập nhật dữ liệu đầu ra...")
    
    master_chutes = {}
    STATIC_CHUTES = [
        # Zone 3
        {"zone": "3", "area_id": "C01", "name": "SG CHỢ LỚN", "capacity": 780},
        {"zone": "3", "area_id": "C02", "name": "SG HƯNG LONG", "capacity": 780},
        {"zone": "3", "area_id": "C03", "name": "SG BÌNH LỢI TRUNG", "capacity": 780},
        {"zone": "3", "area_id": "C04", "name": "SG BÌNH TRỊ ĐÔNG", "capacity": 780},
        {"zone": "3", "area_id": "C05", "name": "SG KHÁNH HỘI", "capacity": 780},
        {"zone": "3", "area_id": "C06", "name": "BD BÌNH PHƯỚC", "capacity": 780},
        {"zone": "3", "area_id": "C07", "name": "DT TN", "capacity": 780},
        {"zone": "3", "area_id": "C08", "name": "TG GÒ CÔNG", "capacity": 780},
        {"zone": "3", "area_id": "C09", "name": "LA HẬU NGHĨA", "capacity": 780},
        {"zone": "3", "area_id": "C10", "name": "AG TỊNH BIÊN", "capacity": 780},
        {"zone": "3", "area_id": "C11", "name": "AG TÂN CHÂU", "capacity": 780},
        {"zone": "3", "area_id": "C12", "name": "AG AN PHÚ", "capacity": 780},
        {"zone": "3", "area_id": "C13", "name": "VL CHỢ LÁCH", "capacity": 780},
        {"zone": "3", "area_id": "C14", "name": "SG NHÀ BÈ", "capacity": 780},
        {"zone": "3", "area_id": "C15", "name": "ST PHÚ LỘC", "capacity": 780},
        {"zone": "3", "area_id": "C16", "name": "CT LONG MỸ", "capacity": 780},
        {"zone": "3", "area_id": "C17", "name": "ST VĨNH CHÂU", "capacity": 780},
        {"zone": "3", "area_id": "C18", "name": "SG GÒ VẤP", "capacity": 780},
        {"zone": "3", "area_id": "C19", "name": "LA BẾN LỨC", "capacity": 780},
        {"zone": "3", "area_id": "C20", "name": "SG XUÂN LỘC", "capacity": 780},
        {"zone": "3", "area_id": "C21", "name": "DC NHÀ BÈ", "capacity": 780},
        {"zone": "3", "area_id": "C22", "name": "DC BÌNH HƯNG", "capacity": 780},
        {"zone": "3", "area_id": "C23", "name": "DC GIA ĐỊNH", "capacity": 780},
        {"zone": "3", "area_id": "C24", "name": "BD BÌNH HÒA", "capacity": 780},
        {"zone": "3", "area_id": "C25", "name": "BD BẾN CÁT", "capacity": 780},
        {"zone": "3", "area_id": "C26", "name": "SETN", "capacity": 780},
        # Zone 2
        {"zone": "3", "area_id": "A00", "name": "VT LONG ĐẤT", "capacity": 780},
        {"zone": "3", "area_id": "A01", "name": "SG HÓC MÔN", "capacity": 780},
        {"zone": "3", "area_id": "A02", "name": "SG BÌNH LỢI", "capacity": 780},
        {"zone": "3", "area_id": "A03", "name": "SG THỦ ĐỨC", "capacity": 780},
        {"zone": "3", "area_id": "A04", "name": "LA ĐỨC HÒA", "capacity": 780},
        {"zone": "2", "area_id": "B01", "name": "SG XUÂN THỚI SƠN", "capacity": 780},
        {"zone": "2", "area_id": "B02", "name": "SG TÂN NHỰT", "capacity": 780},
        {"zone": "2", "area_id": "B03", "name": "SG VĨNH LỘC", "capacity": 780},
        {"zone": "2", "area_id": "B04", "name": "YT XUYÊN MỘC", "capacity": 780},
        {"zone": "2", "area_id": "B05", "name": "YT CHÂU ĐỨC", "capacity": 780},
        {"zone": "2", "area_id": "B06", "name": "AN PHÚ ĐÔNG", "capacity": 780},
        {"zone": "2", "area_id": "B07", "name": "TÂN THỚI HIỆP", "capacity": 780},
        {"zone": "2", "area_id": "B08", "name": "SG TÂN TẠO", "capacity": 780},
        {"zone": "2", "area_id": "B09", "name": "SG CỦ CHI", "capacity": 780},
        {"zone": "2", "area_id": "B10", "name": "SG TÂN SƠN NHÌ", "capacity": 780},
        {"zone": "2", "area_id": "B11", "name": "SG HIỆP BÌNH", "capacity": 780},
        {"zone": "2", "area_id": "B12", "name": "SG PHÚ LÂM", "capacity": 780},
        {"zone": "2", "area_id": "B13", "name": "SG AN LẠC", "capacity": 780},
        {"zone": "2", "area_id": "B14", "name": "SG BÌNH TÂN", "capacity": 780},
        {"zone": "2", "area_id": "B15", "name": "SG TÂN HƯNG", "capacity": 780},
        {"zone": "2", "area_id": "B16", "name": "SG BÀ ĐIỂM", "capacity": 780},
        # Zone 1
        {"zone": "1", "area_id": "A05", "name": "AG LONG XUYÊN", "capacity": 780},
        {"zone": "1", "area_id": "A06", "name": "AG CẦN ĐĂNG", "capacity": 780},
        {"zone": "1", "area_id": "A07", "name": "CT Ô MÔN", "capacity": 780},
        {"zone": "1", "area_id": "A08", "name": "CT BÌNH THỦY", "capacity": 780},
        {"zone": "1", "area_id": "A09", "name": "CT NINH KIỀU", "capacity": 780},
        {"zone": "1", "area_id": "A10", "name": "DT CAO LÃNH", "capacity": 780},
        {"zone": "1", "area_id": "A11", "name": "DT SA ĐÉC", "capacity": 780},
        {"zone": "1", "area_id": "A12", "name": "TG HÒA KHÁNH", "capacity": 780},
        {"zone": "1", "area_id": "A13", "name": "VL VĨNH LONG", "capacity": 780},
        {"zone": "1", "area_id": "A14", "name": "TG AN HỮU", "capacity": 780},
        {"zone": "1", "area_id": "A15", "name": "LA TÂN AN", "capacity": 780},
        {"zone": "1", "area_id": "A16", "name": "TG MỸ THO", "capacity": 780},
        {"zone": "1", "area_id": "A17", "name": "TG TRUNG AN", "capacity": 780},
        {"zone": "1", "area_id": "A18", "name": "VT VŨNG TÀU", "capacity": 780},
        {"zone": "1", "area_id": "A19", "name": "BN HUB", "capacity": 780}
    ]
    for item in STATIC_CHUTES:
        key = (item["zone"], item["area_id"])
        master_chutes[key] = {
            "zone": item["zone"],
            "area_id": item["area_id"],
            "name": item["name"],
            "dai": "8",
            "rong": "4",
            "capacity": str(item["capacity"])
        }

    # Load valid.csv and dynamically rename chutes based on latest mappings
    d_station_to_chute = {}
    d_chute_to_name = {}
    
    try:
        df_valid = pd.read_csv(VALID_FILE, encoding='utf-8-sig', dtype=str)
        df_valid.columns = df_valid.columns.str.strip()
        
        # 1. Dynamically rename master_chutes names
        if 'Bưu cục final' in df_valid.columns and 'area' in df_valid.columns:
            area_to_bc = {}
            for _, row in df_valid.iterrows():
                bc = str(row['Bưu cục final']).strip()
                ar = str(row['area']).strip().upper()
                if bc and ar and ar not in ('OFFLINE', 'NAN', ''):
                    if ar not in area_to_bc:
                        area_to_bc[ar] = []
                    if bc not in area_to_bc[ar]:
                        area_to_bc[ar].append(bc)
            
            for key, info in master_chutes.items():
                c_id = info["area_id"]
                if c_id in area_to_bc:
                    info["name"] = area_to_bc[c_id][0]
                    
        # 2. Build d_station_to_chute and d_chute_to_name mapping dictionaries
        for key, info in master_chutes.items():
            c_id = info["area_id"]
            c_name = info["name"].strip().upper()
            d_chute_to_name[c_id] = c_name
            d_station_to_chute[c_name] = c_id
            
        # 3. Add alternative names from valid.csv
        STATIC_CHUTE_IDS = {item["area_id"].strip().upper() for item in STATIC_CHUTES}
        if 'Bưu cục final' in df_valid.columns and 'area' in df_valid.columns:
            for _, row in df_valid.iterrows():
                bc = str(row['Bưu cục final']).strip().upper()
                ar = str(row['area']).strip().upper()
                if bc and ar and ar in STATIC_CHUTE_IDS:
                    d_station_to_chute[bc] = ar
                    
    except Exception as e_dynamic_rename:
        print(f"   ⚠️ Lỗi dynamic renaming hoặc build maps từ valid.csv: {e_dynamic_rename}")
        # Fallback to static mapping
        for item in STATIC_CHUTES:
            c_id = item["area_id"].strip().upper()
            c_name = item["name"].strip().upper()
            d_chute_to_name[c_id] = c_name
            d_station_to_chute[c_name] = c_id
        
    def map_station_to_layout_name(station_name):
        st_upper = str(station_name).strip().upper()
        chute_id = d_station_to_chute.get(st_upper)
        if chute_id:
            return d_chute_to_name.get(chute_id, st_upper)
        return st_upper

    ss = None
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    local_creds_path = r"C:\Users\lehoa\OneDrive\Desktop\testing\addressproject.json"
    if not creds_json and os.path.exists(local_creds_path):
        try:
            with open(local_creds_path, 'r', encoding='utf-8') as f:
                creds_json = f.read()
        except Exception:
            pass
    if creds_json and not DISABLE_GOOGLE_SHEETS:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
            gc = gspread.authorize(creds)
            ss = gc.open_by_key(SHEET_ID)
        except Exception:
            pass
                
    # Export master_chutes to data/config.json and src/data/config.json for frontend mapping
    try:
        config_list = []
        for (z_k, a_k), m_info in master_chutes.items():
            config_list.append({
                "zone": m_info.get("zone", z_k),
                "areaId": m_info.get("area_id", a_k),
                "buuCuc": m_info.get("name", ""),
                "capacity": int(m_info["capacity"]) if str(m_info.get("capacity", "")).isdigit() else 780,
                "dai": m_info.get("dai", "8"),
                "rong": m_info.get("rong", "4")
            })
        os.makedirs("data", exist_ok=True)
        with open("data/config.json", "w", encoding="utf-8") as f_cfg:
            json.dump(config_list, f_cfg, ensure_ascii=False, indent=2)
        os.makedirs(os.path.join(BASE_DIR, "..", "src", "data"), exist_ok=True)
        with open(os.path.join(BASE_DIR, "..", "src", "data", "config.json"), "w", encoding="utf-8") as f_cfg2:
            json.dump(config_list, f_cfg2, ensure_ascii=False, indent=2)
        print(f"   💾 Đã xuất cấu hình master ({len(config_list)} bưu cục) ra 'data/config.json'.")
    except Exception as e_cfg:
        print(f"   ⚠️ Lỗi xuất config.json: {e_cfg}")

    # 1. Update Outbound Sheet
    if run_outbound and target_dates:
        mapped_outbound_volumes = {}
        if outbound_volumes_grouped:
            for (d_str, station_clean), val in outbound_volumes_grouped.items():
                layout_name = map_station_to_layout_name(station_clean)
                key = (d_str, layout_name)
                if key not in mapped_outbound_volumes:
                    mapped_outbound_volumes[key] = {'volume': 0, 'weight': 0.0}
                mapped_outbound_volumes[key]['volume'] += val.get('volume', 0)
                mapped_outbound_volumes[key]['weight'] += val.get('weight', 0.0)
        update_outbound_sheet(ss, master_chutes, mapped_outbound_volumes, target_dates)
        
    # 2. Update Backlog Sheet (Realtime Pivot)
    # ✅ Dùng thẳng df_bl từ JFS API (real-time) thay vì đọc từ DB cũ tích lũy nhiều ngày
    if run_backlog_inv:
        backlog_volumes = {}
        try:
            raw_bl = results.get('backlog', [])
            if raw_bl:
                df_live_bl = pd.DataFrame(raw_bl)
                # Lọc chỉ đơn đang trong kho
                if 'operate_site_type' in df_live_bl.columns:
                    df_live_bl = df_live_bl[df_live_bl['operate_site_type'] == 'Trong kho']
                if 'billcode' in df_live_bl.columns and 'destination_site_name' in df_live_bl.columns:
                    # Xác định bưu cục đích (giống logic df_bl bên trên)
                    BACKLOG_REDELIVER_REMARKS_LOCAL = {
                        'Người nhận từ chối nhận hàng','Khách không ở địa chỉ giao hàng',
                        'Số điện thoại không liên lạc được','Người nhận đặt trùng đơn / mua nhầm',
                        'Khách từ chối thanh toán','Khách không đặt hàng','Sai số điện thoại',
                        'Khách yêu cầu dùng thử, kiểm hàng','Người nhận hẹn lại thời gian giao hàng',
                        'Địa chỉ khách hàng sai','Hàng hóa hư hỏng một phần','Hàng hóa hư hỏng hoàn toàn'
                    }
                    df_live_bl['dispatch_plan'] = df_live_bl['destination_site_name']
                    if 'abnormal_remark' in df_live_bl.columns and 'take_site_name' in df_live_bl.columns:
                        is_rdlv = df_live_bl['abnormal_remark'].isin(BACKLOG_REDELIVER_REMARKS_LOCAL)
                        df_live_bl.loc[is_rdlv, 'dispatch_plan'] = df_live_bl.loc[is_rdlv, 'take_site_name']
                    df_live_bl['next_station'] = df_live_bl['dispatch_plan'].map(d_buucuc).fillna('')
                    df_live_bl['weight'] = pd.to_numeric(df_live_bl.get('weight', 0), errors='coerce').fillna(0)
                    df_live_bl['next_station_upper'] = df_live_bl['next_station'].astype(str).str.strip().str.upper()
                    df_live_bl['layout_name'] = df_live_bl['next_station_upper'].apply(map_station_to_layout_name)
                    backlog_volumes = df_live_bl.groupby('layout_name').agg(
                        volume=('billcode', 'size'),
                        weight=('weight', 'sum')
                    ).to_dict(orient='index')
                    print(f"   ℹ| Backlog live từ JFS API: {df_live_bl['billcode'].nunique():,} đơn unique")
        except Exception as e_bl_live:
            print(f"   ⚠️ Lỗi tính Backlog pivot từ API: {e_bl_live}")
        update_backlog_sheet(ss, master_chutes, backlog_volumes, current_date_str)
        
    # 3. Update Inventory Sheet (Realtime Pivot)
    if run_backlog_inv:
        inventory_volumes = {}
        try:
            conn = sqlite3.connect(DB_FILE)
            # Đọc toàn bộ shipments từ SQLite
            df_db_inv = pd.read_sql_query(
                "SELECT next_station, status_order, weight, waybillNo, time_ref FROM shipments WHERE status_order != 'Đã rời HUB'",
                conn
            )
            conn.close()
            if not df_db_inv.empty:
                df_db_inv['next_station_upper'] = df_db_inv['next_station'].astype(str).str.strip().str.upper()
                df_db_inv['layout_name'] = df_db_inv['next_station_upper'].apply(map_station_to_layout_name)
                df_db_inv['status_upper'] = df_db_inv['status_order'].astype(str).str.strip()
                inventory_volumes = df_db_inv.groupby(['layout_name', 'status_upper']).agg(
                    volume=('waybillNo', 'size'),
                    weight=('weight', 'sum')
                ).to_dict(orient='index')
        except Exception as e_inv_db:
            print(f"   ⚠️ Lỗi tính Inventory pivot từ SQLite: {e_inv_db}")
        update_inventory_sheet(ss, master_chutes, inventory_volumes, current_date_str)
        
    # 4. Update Inbound Sheets (aggregated Inbound + raw Linehaul + Arrival)
    if results:
        update_inbound_sheets(ss, results, master_chutes, d_buucuc)



# ================================================================
# RECONCILE: Mapping Outbound ngược lại DB (không kéo API 2 lần)
# ================================================================
def reconcile_outbound_5days(raw_outbound=None, session=None, token_mgr=None):
    """
    Mapping log Outbound ngược vào DB: đánh dấu các đơn đã xuất HUB
    là 'Đã rời HUB' (is_active=0).

    - Khi gọi từ run_once(): truyền raw_outbound đã có sẵn → không kéo API thêm.
    - Khi gọi từ startup_sync.py (độc lập): truyền session + token_mgr → tự kéo 5 ngày.
    """
    if raw_outbound is None:
        # Chỉ kéo API khi chạy độc lập (startup_sync, không có data sẵn)
        if not session or not token_mgr:
            print("   ⚠️ [Reconcile Outbound] Không có data và không có session để kéo API.")
            return
        tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
        now   = datetime.now(tz_vn)
        date_start_5d = (now - timedelta(days=5)).strftime('%Y-%m-%d') + ' 00:00:00'
        date_end      = now.strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n🔄 [Reconcile Outbound] Kéo từ API: {date_start_5d} → {date_end}...")
        try:
            oh = load_json(os.path.join(BASE_DIR, "config", "outboundheaders.json"))
            op = load_json(os.path.join(BASE_DIR, "config", "outboundpayload.json"))
            op['beginDate'] = date_start_5d
            op['endDate']   = date_end
            o_params = {
                'sqlCode':   op.get('sqlCode', ''),
                'dcr_key':   '57b048fb-bc8c-4d24-982b-a750b7ce8693',
                'routeName': oh.get('routeName', '')
            }
            raw_outbound = pull_scan(session, token_mgr, URL_SCAN, oh, o_params, op, 'Outbound-5d')
        except Exception as e:
            print(f"   ⚠️ Lỗi kéo Outbound từ API: {e}")
            return
    else:
        print(f"\n🔄 [Reconcile Outbound] Tái sử dụng {len(raw_outbound):,} dòng Outbound đã kéo — không gọi API thêm.")

    if not raw_outbound:
        print("   ⚠️ [Reconcile Outbound] Không có dữ liệu Outbound.")
        return

    # Gom max scan time per waybill
    outbound_map = {}
    for r in raw_outbound:
        wb        = str(r.get('billNo') or r.get('waybillNo') or '').strip()
        scan_time = str(r.get('scanDate') or '').strip()
        next_st   = str(r.get('upOrNextStation') or '').strip()
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in outbound_map or scan_time > outbound_map[wb]['time']:
                outbound_map[wb] = {'time': scan_time, 'station': next_st}

    if not outbound_map:
        print("   ⚠️ [Reconcile Outbound] Không có mã vận đơn hợp lệ.")
        return

    print(f"   📦 {len(outbound_map):,} mã vận đơn có log Outbound → mapping vào DB...")

    # Cập nhật ngược vào DB: đánh dấu Đã rời HUB
    try:
        conn    = sqlite3.connect(DB_FILE)
        c       = conn.cursor()
        updated = 0
        for wb, info in outbound_map.items():
            c.execute("""
                UPDATE shipments
                SET outbound_scanDate = ?,
                    status_order      = 'Đã rời HUB',
                    is_active         = 0,
                    last_updated      = CURRENT_TIMESTAMP
                WHERE waybillNo = ?
                  AND is_active = 1
                  AND (outbound_scanDate = '' OR outbound_scanDate IS NULL
                       OR outbound_scanDate < ?)
            """, (info['time'], wb, info['time']))
            updated += c.rowcount
        conn.commit()
        conn.close()
        print(f"   ✅ [Reconcile Outbound] Cập nhật {updated:,} đơn → 'Đã rời HUB'.")
    except Exception as e:
        print(f"   ⚠️ Lỗi cập nhật DB sau Reconcile Outbound: {e}")


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
    
    last_run_file = os.path.join(BASE_DIR, "db", "last_run.txt")
    last_run_dt = None
    if not is_rebuild and os.path.exists(last_run_file):
        try:
            with open(last_run_file, "r") as f:
                val = f.read().strip()
                if val:
                    last_run_dt = datetime.strptime(val, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz_vn)
        except Exception:
            pass

    if not last_run_dt:
        last_run_dt = now - timedelta(days=2)

    DATE_START_STANDARD = (now - timedelta(days=2)).strftime('%Y-%m-%d') + ' 06:00:00'
    DATE_START_DISPATCH = (last_run_dt - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    DATE_END   = now.strftime('%Y-%m-%d %H:%M:%S')

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
    print(f"📅 Range (Standard): {DATE_START_STANDARD} → {DATE_END}\n📅 Range (Dispatch): {DATE_START_DISPATCH} → {DATE_END}")
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

    print("\n📋 Load Thong_tin_co_ban.csv...")
    d_thong_tin = {}
    tt_file = r"C:\Users\lehoa\.gemini\antigravity\dulieu\Thong_tin_co_ban.csv"
    if not os.path.exists(tt_file):
        tt_file = os.path.join(BASE_DIR, "config", "Thong_tin_co_ban.csv")
    if os.path.exists(tt_file):
        try:
            import pandas as pd
            df_tt = pd.read_csv(tt_file, encoding='utf-8-sig')
            df_tt.columns = df_tt.columns.str.strip()
            for _, row in df_tt.iterrows():
                code = str(row.get('Mã điểm tiếp theo') or '').strip().upper()
                if code:
                    d_thong_tin[code] = {
                        'ten_gd': str(row.get('Tên điểm GD') or '').strip(),
                        'ten_tiep_theo': str(row.get('Tên điểm tiếp theo') or '').strip()
                    }
            print(f"   ✅ Đã nạp {len(d_thong_tin)} mã phân loại từ Thong_tin_co_ban.csv")
        except Exception as ex_tt:
            print(f"   ⚠️ Lỗi nạp Thong_tin_co_ban.csv: {ex_tt}")
    else:
        print(f"   ⚠️ Không tìm thấy Thong_tin_co_ban.csv tại {tt_file}")

    print("\n🔐 Kiểm tra token (in-memory)...")
    if not token_mgr.get_token():
        print("❌ Không lấy được token.")
        return

    # Khởi tạo session và TokenManager riêng biệt cho nguồn Arrival sử dụng tài khoản 660085 (tránh xung đột cookies/session với user 660021)
    print("🔐 Khởi tạo session & TokenManager riêng biệt cho Arrival (User: 660085)...")
    arrival_session = build_session()
    arrival_token_mgr = TokenManager(arrival_session, "660085", "246@Hoang", COUNTRY_ID)
    try:
        arrival_token_mgr.get_token()
    except Exception as e_login_arr:
        print(f"⚠️ Lỗi login tài khoản 660085 cho Arrival: {e_login_arr}. Sẽ tự động thử lại khi chạy.")

    fh = load_json(os.path.join(BASE_DIR, "config", "forecastheaders.json"))
    fp = load_json(os.path.join(BASE_DIR, "config", "forecastpayload.json"))
    for k in ['timeStart', 'inputTimeStart']: fp[k] = DATE_START_STANDARD
    for k in ['timeEnd', 'inputTimeEnd']:     fp[k] = DATE_END

    ih = load_json(os.path.join(BASE_DIR, "config", "inboundheaders.json"))
    ip = load_json(os.path.join(BASE_DIR, "config", "inboundpayload.json"))
    ip['beginDate'] = DATE_START_STANDARD; ip['endDate'] = DATE_END
    i_params = {'sqlCode': ip.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': ih.get('routeName', '')}

    oh = load_json(os.path.join(BASE_DIR, "config", "outboundheaders.json"))
    op = load_json(os.path.join(BASE_DIR, "config", "outboundpayload.json"))
    op['beginDate'] = DATE_START_STANDARD; op['endDate'] = DATE_END
    o_params = {'sqlCode': op.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': oh.get('routeName', '')}

    bh = load_json(os.path.join(BASE_DIR, "config", "backlogheaders.json"))
    bp = load_json(os.path.join(BASE_DIR, "config", "backlogpayload.json"))
    if bp.get('endDate', '').upper() == 'AUTO': bp['endDate'] = DATE_END
    b_params = {'sqlCode': bp.get('sqlCode', ''), 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693', 'routeName': bh.get('routeName', '')}

    dh = load_json(os.path.join(BASE_DIR, "config", "dispatchheaders.json"))
    dp_cfg = load_json(os.path.join(BASE_DIR, "config", "dispatchpayload.json"))
    dp_cfg['startInputTime'] = DATE_START_DISPATCH; dp_cfg['endInputTime'] = DATE_END

    lh_h = load_json(os.path.join(BASE_DIR, "config", "linehaulheaders.json"))
    lh_p = load_json(os.path.join(BASE_DIR, "config", "linehaulpayload.json"))
    lh_p['startScanTime'] = DATE_START_STANDARD
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
            ex.submit(pull_arrival_from_jfs, arrival_session, arrival_token_mgr, ih, DATE_START_STANDARD, DATE_END): 'arrival',
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

    # Load active records from SQLite
    db_records = {}
    init_db()
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Tự động dọn dẹp các đơn kẹt quá 3 ngày không có log xuất kho
        # 1. Đối với các đơn đã quét Inbound
        c.execute("""
            UPDATE shipments 
            SET status_order = 'Đã rời HUB', is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate != '' AND inbound_scanDate IS NOT NULL)
              AND datetime(inbound_scanDate) < datetime('now', '+7 hours', '-3 days')
        """)
        cnt1 = c.rowcount
        
        # 2. Đối với các đơn mới chỉ ở trạng thái Forecast/Pickup (chưa có inbound scan)
        c.execute("""
            UPDATE shipments 
            SET is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
              AND (
                (Pickup_time != '' AND Pickup_time IS NOT NULL AND datetime(Pickup_time) < datetime('now', '+7 hours', '-3 days'))
                OR
                ((Pickup_time = '' OR Pickup_time IS NULL) AND date(time_ref) < date('now', '+7 hours', '-3 days'))
              )
        """)
        cnt2 = c.rowcount

        # 3. Đối với các đơn chỉ từ nguồn Dispatch (không có inbound, không có Pickup_time)
        #    mà dispatchNetworkTime đã quá 2 ngày → hết hiệu lực
        c.execute("""
            UPDATE shipments
            SET is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND data_source = 'Dispatch'
              AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
              AND (outbound_scanDate = '' OR outbound_scanDate IS NULL)
              AND (Pickup_time = '' OR Pickup_time IS NULL)
              AND dispatchNetworkTime != '' AND dispatchNetworkTime IS NOT NULL
              AND datetime(dispatchNetworkTime) < datetime('now', '+7 hours', '-2 days')
        """)
        cnt3 = c.rowcount
        conn.commit()
        if cnt3 > 0:
            print(f"   🧹 Dọn dẹp Dispatch cũ: Đã tắt {cnt3:,} đơn Dispatch không có inbound/pickup quá 2 ngày.")

        if cnt1 + cnt2 + cnt3 > 0:
            print(f"   🧹 Tự động dọn dẹp: Đã chuyển {cnt1:,} đơn kẹt Inbound → 'Đã rời HUB', tắt {cnt2:,} đơn Forecast/Pickup cũ (>3 ngày), tắt {cnt3:,} đơn Dispatch cũ (>2 ngày).")
            
        c.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows = c.fetchall()
        if rows:
            col_names = [description[0] for description in c.description]
            for r in rows:
                rec = dict(zip(col_names, r))
                db_records[rec['waybillNo']] = rec
        conn.close()
        print(f"   ℹ| Load được {len(db_records):,} đơn active từ SQLite.")
    except Exception as e_db:
        print(f"   ⚠️ Lỗi load đơn từ SQLite: {e_db}")

    def get_or_create_record(wb):
        if wb in db_records:
            return db_records[wb], False
            
        conn_check = sqlite3.connect(DB_FILE)
        c_check = conn_check.cursor()
        c_check.execute("SELECT * FROM shipments WHERE waybillNo = ?", (wb,))
        row = c_check.fetchone()
        if row:
            col_names = [description[0] for description in c_check.description]
            rec = dict(zip(col_names, row))
            conn_check.close()
            db_records[wb] = rec
            return rec, False
            
        conn_check.close()
        rec = {
            'waybillNo': wb, 'data_source': '', 'weight': 0.0, 'pickNetworkName': '', 'dispatch_plan': '',
            'Pickup_time': '', 'pickup_label': '', 'Pickup_ontime': '', 'dispatchNetworkTime': '',
            'next_station': '', 'Tuyến': '', 'Rank': '', 'inbound_network': '', 'inbound_scanDate': '',
            'outbound_scanDate': '', 'Arrival_time': '', 'dispatch_actual': '', 'status_order': '', 'time_ref': '',
            'is_backlog': 0, 'is_active': 1
        }
        db_records[wb] = rec
        return rec, True

    # 1. Process Forecast
    df_fc = pd.DataFrame(results.get('forecast', []))
    if not df_fc.empty:
        for _, r in df_fc.iterrows():
            wb = str(r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            rec, _ = get_or_create_record(wb)
            rec['data_source'] = 'Forecast'
            rec['pickNetworkName'] = d_buucuc.get(str(r.get('pickNetworkName', '')).strip(), str(r.get('pickNetworkName', '')).strip())
            disp_plan = str(r.get('dispatchNetworkName') or '').strip()
            if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                disp_plan = str(r.get('terminalDispatchCode') or r.get('transferDispatchCode') or r.get('receiverSortingCode') or '').strip()
            rec['dispatch_plan'] = disp_plan
            rec['weight'] = float(r.get('loadWeight') or r.get('weight') or rec['weight'])
            
            delivery_time = str(r.get('deliveryTime') or '').strip()
            if delivery_time and delivery_time.lower() not in ('nan', 'none'):
                rec['Pickup_time'] = delivery_time
            rec['changed'] = True

    # 2. Process Dispatch
    df_dp = pd.DataFrame(results.get('dispatch', []))
    if not df_dp.empty:
        for _, r in df_dp.iterrows():
            wb = str(r.get('waybillId') or r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            rec, _ = get_or_create_record(wb)
            rec['data_source'] = 'Dispatch'
            rec['pickNetworkName'] = d_buucuc.get(str(r.get('pickNetworkName', '')).strip(), str(r.get('pickNetworkName', '')).strip())
            disp_plan = str(r.get('dispatchNetworkName') or '').strip()
            if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                disp_plan = str(r.get('terminalDispatchCode') or r.get('transferDispatchCode') or r.get('receiverSortingCode') or '').strip()
            rec['dispatch_plan'] = disp_plan
            rec['weight'] = float(r.get('packageChargeWeight') or r.get('weight') or rec['weight'])
            
            disp_time = str(r.get('dispatchNetworkTime') or '').strip()
            if disp_time and disp_time.lower() not in ('nan', 'none'):
                rec['dispatchNetworkTime'] = disp_time
                
            status_dp = str(r.get('orderStatusName') or '').strip()
            update_time = str(r.get('updateTime') or '').strip()
            if status_dp == 'Đã lấy hàng' and update_time and update_time.lower() not in ('nan', 'none'):
                rec['Pickup_time'] = update_time
                
            rec['changed'] = True

    # 3. Process Arrival Scans (Max scan time per waybill)
    arrival_raw = results.get('arrival', [])
    arrival_max = {}
    for r in arrival_raw:
        wb = str(r.get('billcode') or r.get('waybillNo') or r.get('billNo') or '').strip()
        scan_time = str(r.get('scantime') or '').strip()
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in arrival_max or scan_time > arrival_max[wb]:
                arrival_max[wb] = scan_time
                
    for wb, scan_time in arrival_max.items():
        rec, _ = get_or_create_record(wb)
        if not rec['data_source']:
            rec['data_source'] = 'Arrival'
        if not rec['Arrival_time'] or scan_time > rec['Arrival_time']:
            rec['Arrival_time'] = scan_time
            rec['changed'] = True

    # 4. Process Inbound Scans (Max scan time per waybill)
    inbound_raw = results.get('inbound', [])
    inbound_max = {}
    for r in inbound_raw:
        wb = str(r.get('billNo') or r.get('waybillNo') or '').strip()
        scan_time = str(r.get('scanDate') or '').strip()
        send_site = str(r.get('sendSite') or '').strip()
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in inbound_max or scan_time > inbound_max[wb]['time']:
                inbound_max[wb] = {'time': scan_time, 'site': send_site}
                
    for wb, info in inbound_max.items():
        rec, _ = get_or_create_record(wb)
        if not rec['data_source']:
            rec['data_source'] = 'Inbound'
        if not rec['inbound_scanDate'] or info['time'] > rec['inbound_scanDate']:
            rec['inbound_scanDate'] = info['time']
            rec['inbound_network'] = d_buucuc.get(info['site'], info['site'])
            rec['changed'] = True

    # 5. Process Outbound Scans (Max scan time per waybill)
    outbound_raw = results.get('outbound', [])
    outbound_max = {}
    for r in outbound_raw:
        wb = str(r.get('billNo') or r.get('waybillNo') or '').strip()
        scan_time = str(r.get('scanDate') or '').strip()
        next_station = str(r.get('upOrNextStation') or '').strip()
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in outbound_max or scan_time > outbound_max[wb]['time']:
                outbound_max[wb] = {'time': scan_time, 'station': next_station}
                
    for wb, info in outbound_max.items():
        rec, _ = get_or_create_record(wb)
        if not rec['outbound_scanDate'] or info['time'] > rec['outbound_scanDate']:
            rec['outbound_scanDate'] = info['time']
            rec['dispatch_actual'] = d_buucuc.get(info['station'], info['station'])
            rec['changed'] = True

    # 6. Process Backlog
    BACKLOG_REDELIVER_REMARKS = {
        'Người nhận từ chối nhận hàng', 'Khách không ở địa chỉ giao hàng', 'Số điện thoại không liên lạc được',
        'Người nhận đặt trùng đơn / mua nhầm', 'Khách từ chối thanh toán', 'Khách không đặt hàng', 'Sai số điện thoại',
        'Khách yêu cầu dùng thử, kiểm hàng', 'Người nhận hẹn lại thời gian giao hàng', 'Địa chỉ khách hàng sai',
        'Hàng hóa hư hỏng một phần', 'Hàng hóa hư hỏng hoàn toàn'
    }
    raw_bl = results.get('backlog', [])
    for r in raw_bl:
        wb = str(r.get('billcode') or '').strip()
        if not wb:
            continue
        site_type = str(r.get('operate_site_type') or '').strip()
        if site_type != 'Trong kho':
            continue
        rec, _ = get_or_create_record(wb)
        rec['is_backlog'] = 1
        rec['outbound_scanDate'] = ''
        
        dest = str(r.get('destination_site_name') or '').strip()
        abn = str(r.get('abnormal_remark') or '').strip()
        if abn in BACKLOG_REDELIVER_REMARKS:
            take_site = str(r.get('take_site_name') or '').strip()
            if take_site:
                dest = take_site
        dest_mapped = d_buucuc.get(dest, dest)
        rec['dispatch_plan'] = dest
        rec['next_station'] = dest_mapped
        rec['changed'] = True

    # 7. Batch search Dispatch time for Forecast / Inbound waybills
    missing_disp_wbs = []
    for wb, rec in db_records.items():
        if (not rec.get('dispatch_plan') or not rec.get('dispatchNetworkTime')) and rec.get('status_order') != 'Đã rời HUB':
            missing_disp_wbs.append(wb)
            
    missing_disp_wbs = list(set(missing_disp_wbs))[:3500]
    if missing_disp_wbs:
        print(f"\n🔍 [Batch Search] Phát hiện {len(missing_disp_wbs):,} đơn Forecast/Inbound chưa có dispatch_plan hoặc dispatchNetworkTime.")
        dh_path = os.path.join(BASE_DIR, "config", "dispatchheaders.json")
        dp_path = os.path.join(BASE_DIR, "config", "dispatchpayload.json")
        if os.path.exists(dh_path) and os.path.exists(dp_path):
            try:
                dh = load_json(dh_path)
                dp_cfg = load_json(dp_path)
                dispatch_session = build_session()
                dispatch_token_mgr = TokenManager(dispatch_session, token_mgr.account, token_mgr.password, token_mgr.country_id)
                
                dh['authToken'] = dispatch_token_mgr.get_token()
                dh['Authtoken'] = dispatch_token_mgr.get_token()
                dh['Routename'] = 'orderScheduling'
                dh['routeName'] = 'orderScheduling'
                
                chunk_size = 50
                resolved_disp = {}
                resolved_wbs = set()
                
                for i in range(0, len(missing_disp_wbs), chunk_size):
                    chunk = missing_disp_wbs[i:i+chunk_size]
                    payload = dp_cfg.copy()
                    payload['waybillIds'] = ",".join(chunk)
                    payload['current'] = 1
                    payload['size'] = len(chunk)
                    
                    for k in ['startInputTime', 'endInputTime', 'startPickTime', 'endPickTime']:
                        if k in payload:
                            payload[k] = ""
                            
                    try:
                        r_dp = auth_post(dispatch_session, URL_DISPATCH, dispatch_token_mgr, dh, data=payload, timeout=25, label=f'Batch Dispatch {i//chunk_size}')
                        dp_res = r_dp.json()
                        data_node = dp_res.get('data', {})
                        records = []
                        if isinstance(data_node, dict):
                            records = data_node.get('records', []) or []
                        elif isinstance(data_node, list):
                            records = data_node
                            
                        if records:
                            for item in records:
                                if not isinstance(item, dict):
                                    continue
                                waybill_id = str(item.get('waybillId') or '').strip()
                                if waybill_id:
                                    disp_time = str(item.get('dispatchNetworkTime') or item.get('inputTime') or item.get('createTime') or '').strip()
                                    pickup_time = str(item.get('updateTime') or '').strip()
                                    order_status = str(item.get('orderStatusName') or '').strip()
                                    
                                    pk_val = pickup_time if (order_status == 'Đã lấy hàng' and pickup_time) else ''
                                    
                                    disp_plan = str(item.get('dispatchNetworkName') or '').strip()
                                    if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                                        disp_plan = str(item.get('terminalDispatchCode') or item.get('transferDispatchCode') or item.get('receiverSortingCode') or '').strip()
                                    
                                    if disp_time and disp_time.lower() not in ('nan', 'none', 'nat', ''):
                                        resolved_disp[waybill_id] = {
                                            'dispatchNetworkTime': disp_time,
                                            'Pickup_time': pk_val,
                                            'status_order': order_status,
                                            'dispatch_plan': disp_plan
                                        }
                                        resolved_wbs.add(waybill_id)
                    except Exception as e_batch:
                        print(f"      ⚠️ Lỗi query batch chunk {i//chunk_size}: {e_batch}")
                        
                print(f"   ✅ [Batch Search] Hoàn tất: Tìm thấy thông tin Dispatch cho {len(resolved_disp):,} / {len(missing_disp_wbs):,} đơn.")
                
                for wb, info in resolved_disp.items():
                    if wb in db_records:
                        db_records[wb]['dispatchNetworkTime'] = info['dispatchNetworkTime']
                        if info['Pickup_time']:
                            db_records[wb]['Pickup_time'] = info['Pickup_time']
                        if info.get('dispatch_plan'):
                            db_records[wb]['dispatch_plan'] = info['dispatch_plan']
                        db_records[wb]['data_source'] = 'Dispatch'
                        db_records[wb]['changed'] = True
                        
            except Exception as e_setup:
                print(f"   ❌ Lỗi cấu hình Batch search: {e_setup}")
    # ================================================================

    # All changes are already merged in db_records, we just need to normalize and clean fields
    for wb, rec in db_records.items():
        if rec.get('changed'):
            for key in ['inbound_scanDate', 'Pickup_time', 'dispatchNetworkTime', 'outbound_scanDate', 'time_ref']:
                val = rec.get(key)
                if val is None or pd.isna(val):
                    rec[key] = ""
                else:
                    val_str = str(val).strip()
                    if val_str.lower() in ('nan', 'none', 'nat', ''):
                        rec[key] = ""
                    else:
                        rec[key] = val_str

    # Calculate status and derived fields for modified records
    for wb, rec in db_records.items():
        if not rec.get('changed'):
            continue
            
        ib_time = rec['inbound_scanDate']
        pk_time = rec['Pickup_time']
        fc_time = rec['dispatchNetworkTime']
        ob_time = rec['outbound_scanDate']
        arr_time = rec.get('Arrival_time', '')
        
        # Get status using the unified priority engine
        status, is_act = calculate_shipment_status(fc_time, pk_time, arr_time, ib_time, ob_time)
        
        # Outbound logic filter:
        # If in live Backlog (Trong kho) -> enforce 'Đang trên bãi' and clear outbound scan
        if rec.get('is_backlog') or rec.get('data_source') == 'Backlog':
            status = 'Đang trên bãi'
            rec['outbound_scanDate'] = ''
            ob_time = ''
            is_act = 1
            if not ib_time or ib_time.lower() in ('nan', 'none', ''):
                rec['inbound_scanDate'] = 'Backlog'
                ib_time = 'Backlog'
            
        rec['status_order'] = status
        rec['is_active'] = is_act
        
        # Next station details
        raw_code = str(rec.get('dispatch_plan') or '').strip()
        if not raw_code:
            raw_code = str(rec.get('next_station') or '').strip()

        mapped_ns = ""
        
        # 1. Check for hyphen prefix mapping (e.g. 001-HCM048A)
        if '-' in raw_code:
            parts = raw_code.split('-')
            if len(parts) > 1:
                clean_code = parts[1].strip().upper()
                if clean_code in d_thong_tin:
                    info = d_thong_tin[clean_code]
                    tgd = info['ten_gd']
                    ttt = info['ten_tiep_theo']
                    if 'HCM' in tgd:
                        mapped_ns = ttt
                    elif 'BN HUB' in tgd:
                        mapped_ns = 'BN HUB'
                    else:
                        mapped_ns = tgd

        # 2. Fallback to normal valid.csv maps if not matched yet
        if not mapped_ns:
            code_upper = raw_code.upper()
            if code_upper in d_sortcode:
                mapped_ns = d_sortcode[code_upper]
            elif code_upper in d_buucuc:
                mapped_ns = d_buucuc[code_upper]
            else:
                # Try fallback on the clean split code
                if '-' in raw_code:
                    clean_code = raw_code.split('-')[1].strip().upper()
                    if clean_code in d_sortcode:
                        mapped_ns = d_sortcode[clean_code]
                    elif clean_code in d_buucuc:
                        mapped_ns = d_buucuc[clean_code]

        # 3. Default to Hubs if next_station is still empty
        pkn = str(rec.get('pickNetworkName') or '').strip()
        NORTH_POST_OFFICES = {
            'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
            'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
            'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
            'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
            'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
            'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
            'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
        }

        if not mapped_ns or mapped_ns.lower() in ('nan', 'none', ''):
            if pkn in NORTH_POST_OFFICES or pkn.startswith('HN ') or pkn.startswith('HD ') or pkn.startswith('HY '):
                mapped_ns = 'BN HUB'
            else:
                mapped_ns = 'HCM HUB'

        rec['next_station'] = mapped_ns

        # Map Tuyến and Rank
        if mapped_ns == 'BN HUB':
            rec['Tuyến'] = 'Linehaul'
            rec['Rank'] = 'BN HUB'
        elif mapped_ns == 'HCM HUB':
            rec['Tuyến'] = 'Linehaul'
            rec['Rank'] = 'HCM HUB'
        else:
            rec['Tuyến'] = d_tuyen.get(mapped_ns, '')
            rec['Rank'] = d_rank.get(mapped_ns, '')
        
        # time_ref
        t_ref = ob_time if ob_time else (ib_time if ib_time else (pk_time if pk_time else fc_time))
        rec['time_ref'] = t_ref
        
        # pickup_label & Pickup_ontime
        disp = fc_time
        pick = pk_time
        p_lbl = ''
        p_ont = ''
        if disp and disp != 'nan' and pick and pick != 'nan':
            try:
                d_disp = disp[:10]
                d_pick = pick[:10]
                if d_disp == d_pick:
                    p_lbl = 'Lấy trong ngày'
                    p_ont = 'YES'
                elif d_disp < d_pick:
                    p_lbl = 'Lấy ngày hôm sau'
                    p_ont = 'NO'
                else:
                    p_ont = 'NO'
            except Exception:
                pass
        rec['pickup_label'] = p_lbl
        rec['Pickup_ontime'] = p_ont

    # Extract modified records to UPSERT
    changed_records = []
    for wb, rec in db_records.items():
        if rec.get('changed'):
            changed_records.append([
                rec['waybillNo'], rec['data_source'], rec['weight'], rec['pickNetworkName'], rec['dispatch_plan'],
                rec['Pickup_time'], rec['pickup_label'], rec['Pickup_ontime'], rec['dispatchNetworkTime'],
                rec['next_station'], rec['Tuyến'], rec['Rank'], rec['inbound_network'], rec['inbound_scanDate'],
                rec['outbound_scanDate'], rec.get('Arrival_time', ''), rec['dispatch_actual'], rec['status_order'], rec['time_ref'],
                int(rec.get('is_backlog', 0)), int(rec.get('is_active', 1))
            ])

    if changed_records:
        init_db()
        print(f"\n💾 Đang lưu {len(changed_records):,} bản ghi thay đổi vào SQLite Database cục bộ...")
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = OFF")
            c.execute("PRAGMA cache_size = -64000")
            c.execute("PRAGMA temp_store = MEMORY")
            
            c.executemany("""
                INSERT INTO shipments (
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, Arrival_time, dispatch_actual, status_order, time_ref,
                    is_backlog, is_active, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(waybillNo) DO UPDATE SET
                    data_source        = excluded.data_source,
                    weight             = excluded.weight,
                    pickNetworkName    = excluded.pickNetworkName,
                    dispatch_plan      = excluded.dispatch_plan,
                    Pickup_time        = excluded.Pickup_time,
                    pickup_label       = excluded.pickup_label,
                    Pickup_ontime      = excluded.Pickup_ontime,
                    dispatchNetworkTime= excluded.dispatchNetworkTime,
                    next_station       = excluded.next_station,
                    Tuyến              = excluded.Tuyến,
                    Rank               = excluded.Rank,
                    inbound_network    = excluded.inbound_network,
                    inbound_scanDate   = excluded.inbound_scanDate,
                    outbound_scanDate  = excluded.outbound_scanDate,
                    Arrival_time       = excluded.Arrival_time,
                    dispatch_actual    = excluded.dispatch_actual,
                    status_order       = excluded.status_order,
                    time_ref           = excluded.time_ref,
                    is_backlog         = excluded.is_backlog,
                    is_active          = excluded.is_active,
                    last_updated       = CURRENT_TIMESTAMP
            """, changed_records)
            conn.commit()
            conn.close()
            print(f"   ✅ Đã UPSERT thành công {len(changed_records)} bản ghi thay đổi vào SQLite.")
        except Exception as ex_db:
            print(f"   ❌ Lỗi lưu dữ liệu thay đổi vào SQLite: {ex_db}")

    # ── Reconcile: Mapping Outbound đã kéo ngược lại DB ──
    # Tái sử dụng results['outbound'] đã kéo ở bước trên → KHÔNG gọi API thêm lần nữa
    try:
        reconcile_outbound_5days(raw_outbound=results.get('outbound', []))
    except Exception as e_reconcile:
        print(f"   ⚠️ Lỗi Reconcile Outbound: {e_reconcile}")


    # ── Reload DB sau khi reconcile để df phản ánh đúng trạng thái mới nhất ──
    try:
        conn_r = sqlite3.connect(DB_FILE)
        c_r    = conn_r.cursor()
        c_r.execute("SELECT * FROM shipments WHERE is_active = 1")
        rows_r = c_r.fetchall()
        if rows_r:
            col_names_r = [d[0] for d in c_r.description]
            db_records  = {dict(zip(col_names_r, rw))['waybillNo']: dict(zip(col_names_r, rw)) for rw in rows_r}
        conn_r.close()
        print(f"   ✅ Reload DB sau reconcile: {len(db_records):,} đơn active còn lại.")
    except Exception as e_reload:
        print(f"   ⚠️ Lỗi reload DB sau reconcile: {e_reload}")

    # Build df of all records from SQLite for downstream push / sheets

    df = pd.DataFrame(list(db_records.values()))
    if 'changed' in df.columns:
        df.drop(columns=['changed'], inplace=True)

    def get_op_date_clean(dt_str):
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

    df['Ngày vận hành_Inbound'] = df['inbound_scanDate'].apply(get_op_date_clean)
    
    def calc_fc_op_date(row):
        fc_time = row.get('dispatchNetworkTime')
        if not fc_time or str(fc_time).strip() in ('', 'nan', 'None'):
            if row.get('status_order') == 'Forecast':
                fc_time = row.get('Pickup_time')
        return get_op_date_clean(fc_time)
        
    df['Ngày vận hành_Forecast'] = df.apply(calc_fc_op_date, axis=1)
    
    def calc_pk_op_date(row):
        if row.get('status_order') == 'Forecast':
            return ""
        return get_op_date_clean(row.get('Pickup_time'))
        
    df['Ngày vận hành_Pickup'] = df.apply(calc_pk_op_date, axis=1)

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

    # ================================================================
    # ⚡ PUSH DATA LÊN GITHUB RAW (thay thế Google Sheet cho 100k rows)
    # Dashboard JS sẽ đọc trực tiếp từ raw.githubusercontent.com
    # ================================================================
    print("\n🚀 Đang lưu và nén dữ liệu thô ra local...")
    os.makedirs("data", exist_ok=True)
    df.to_json("data/latest.json.gz", orient="records", force_ascii=False, compression="gzip")
    # push_json_to_github(df, GH_TOKEN, GH_REPO, GH_DATA_PATH)
    
    # print("\n💾 Đang đồng bộ hóa Database SQLite lên Github...")
    # push_db_to_github(DB_FILE, GH_TOKEN, GH_REPO, "backend_sync/db/state.db")

    # Cập nhật dữ liệu cấu hình lên Google Sheets (config sheets, Linehaul, Arrival, Outbound)
    # Data chính (100k rows) đã được push lên Github — không cần ghi vào Sheet nữa
    update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, now.strftime('%Y-%m-%d'), results, d_buucuc, session, token_mgr, fh, fp)
    
    # Write last successful run timestamp
    try:
        with open(last_run_file, "w") as f:
            f.write(now.strftime('%Y-%m-%d %H:%M:%S'))
        print(f"   ✅ Đã ghi nhận thời gian chạy cuối: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e_lr:
        print(f"   ⚠️ Lỗi ghi file last_run.txt: {e_lr}")


# ================================================================
# MERGED: GIAM SAT PHAT HANG — Chạy song song với run_once
# (tích hợp toàn bộ từ scripts/giam_sat_phat_hang.py)
# ================================================================
def run_giam_sat_phat_hang(session: requests.Session, token_mgr: 'TokenManager'):
    """
    Fetch dữ liệu giám sát phát hàng từ tất cả bưu cục HCM/SE gửi về HCM HUB,
    rồi ghi lên sheet Arrival (tích lũy theo ngày + trạm + giờ).
    
    Logic từ giam_sat_phat_hang.py nhưng:
      - Dùng chung session/TokenManager với run_once (không cần login lại).
      - Dùng API Select để lấy station code (đảm bảo chính xác hơn valid.csv).
      - Thêm upsert_arrival để tích lũy lịch sử 7 ngày vào Google Sheet.
    """
    print("\n" + "="*60)
    print("📦 GIAM SAT PHAT HANG: Bắt đầu fetch dữ liệu phát hàng...")
    print("="*60)

    gsh_headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=utf-8",
        "Origin": "https://jfs.jtcargo.com.vn",
        "Referer": "https://jfs.jtcargo.com.vn/",
        "Routename": "Bd-theme-1d2e14d9-6dcc-437e-afb2-0afc668d7d50|businessIndicatorIndex",
        "User-Agent": LOGIN_HEADERS["User-Agent"],
    }

    # — Đọc danh sách bưu cục từ stations_master.csv —
    MASTER_PATH = r"C:\Users\lehoa\OneDrive\Desktop\testing\stations_master.csv"
    # Fallback: tìm trong backend_sync/config/
    if not os.path.exists(MASTER_PATH):
        MASTER_PATH = os.path.join(BASE_DIR, "config", "stations_master.csv")

    if not os.path.exists(MASTER_PATH):
        print(f"   ⚠️ Không tìm thấy stations_master.csv tại {MASTER_PATH}. Bỏ qua Giam sat phat hang.")
        return

    df_stations = pd.read_csv(MASTER_PATH)
    hcm_stations = df_stations[
        df_stations['master_area'].str.contains('HCM|SE', na=False, case=False) |
        df_stations['station_name'].str.contains('BN HUB', na=False, case=False)
    ]
    station_names = hcm_stations['station_name'].dropna().unique().tolist()
    print(f"   📂 Đọc được {len(station_names)} bưu cục (HCM/SE + BN HUB) từ stations_master.csv")

    # Thời gian hôm nay
    today_str  = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d')
    start_time = f"{today_str} 00:00:00"
    end_time   = f"{today_str} 23:59:59"
    print(f"   📅 Lọc ngày: {start_time} → {end_time}")

    # — Bước 1: Tra cứu mã bưu cục song song qua JFS Select API —
    # workers=3 để tránh rate-limit 401 khi gọi nhiều request cùng lúc
    print("   🔍 Tra cứu mã JFS bưu cục (song song, giới hạn 3 workers)...")
    valid_stations = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        future_map = {ex.submit(get_station_info, session, token_mgr, gsh_headers, name): name
                      for name in station_names}
        for fut in as_completed(future_map):
            try:
                info = fut.result()
                if info:
                    valid_stations.append(info)
            except Exception as e:
                print(f"   ⚠️ Lỗi tra cứu trạm {future_map[fut]}: {e}")

    print(f"   ✅ Tìm được mã JFS cho {len(valid_stations)}/{len(station_names)} bưu cục")
    if not valid_stations:
        print("   ⚠️ Không có bưu cục hợp lệ. Bỏ qua.")
        return

    # — Bước 2: Fetch dữ liệu phát hàng song song —
    GSH_PARAMS = {'sqlCode': 'realtime_sca_sen_mon_dtl', 'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693'}
    all_data = []
    lock     = threading.Lock()

    def fetch_one_station(station):
        payload = {
            'beginDate': start_time, 'endDate': end_time,
            'nextStationCode': 'HCM004H', 'nextStationCodeId': 11888,
            'nextStationCodeName': 'HCM HUB', 'nextStationCodeTypeId': 335,
            'countryId': '1', 'size': 1000,
            'sqlCode': 'realtime_sca_sen_mon_dtl',
            'scanSiteCode':       station['code'],
            'scanSiteCodeId':     station['id'],
            'scanSiteCodeName':   station['name'],
            'scanSiteCodeTypeId': station['typeId'],
        }
        station_rows = []
        try:
            # Lấy total trước
            count_pl = {**payload, 'paginationSearchType': 'count', 'size': 1, 'current': 1}
            r_c = auth_post(session, URL_ARRIVAL_SCAN, token_mgr, gsh_headers,
                            params=GSH_PARAMS, json_body=count_pl,
                            label=f'GSH count {station["name"]}')
            total = (r_c.json().get('data') or {}).get('total') or 0
            if not total:
                return
            n_pages = math.ceil(total / 1000)
            # Kéo từng trang
            for p in range(1, n_pages + 1):
                list_pl = {**payload, 'paginationSearchType': 'list', 'current': p}
                r_l = auth_post(session, URL_ARRIVAL_SCAN, token_mgr, gsh_headers,
                                params=GSH_PARAMS, json_body=list_pl,
                                label=f'GSH {station["name"]} p{p}')
                data_node = r_l.json().get('data')
                records = (data_node.get('records', []) if isinstance(data_node, dict)
                           else (data_node or []))
                station_rows.extend(records)
        except Exception as e:
            print(f'   ❌ GSH {station["name"]}: {e}')
        if station_rows:
            with lock:
                all_data.extend(station_rows)
            print(f'   ✅ GSH [{station["name"]}]: {len(station_rows):,} dòng')

    print(f"   🚀 Fetch song song {len(valid_stations)} bưu cục...")
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        list(ex.map(fetch_one_station, valid_stations))

    if not all_data:
        print("   ⚠️ Không có dữ liệu phát hàng nào. Bỏ qua.")
        return

    print(f"   📋 Tổng: {len(all_data):,} dòng từ {len(valid_stations)} bưu cục")

    # — Bước 3: Xử lý DataFrame —
    df_gsh = pd.DataFrame(all_data)

    # Bug fix: DataFrame không có .get() — dùng [] với fallback
    if 'scantime' not in df_gsh.columns:
        print("   ⚠️ Không có cột 'scantime' trong dữ liệu. Bỏ qua.")
        return

    df_gsh['scantime_dt']   = pd.to_datetime(df_gsh['scantime'], errors='coerce')
    df_gsh['Ngày vận hành'] = (df_gsh['scantime_dt'] - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
    # Bug fix: Scan Hour phải là int nhất quán để upsert_arrival so sánh đúng
    df_gsh['Scan Hour']     = df_gsh['scantime_dt'].dt.hour.fillna(0).astype(int)

    # Bug fix: guard check cột Pickup_station
    if 'scansitename' in df_gsh.columns:
        df_gsh = df_gsh.rename(columns={'scansitename': 'Pickup_station'})
    elif 'Pickup_station' not in df_gsh.columns:
        print("   ⚠️ Không có cột 'scansitename'/'Pickup_station'. Bỏ qua.")
        return

    # — Bước 4: Mapping "Đã đến Hub" từ Sheet Inbound —
    try:
        url_ib = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
                  f"/gviz/tq?tqx=out:csv&sheet=Inbound")
        r_ib = requests.get(url_ib, timeout=30)
        r_ib.raise_for_status()
        df_ib = pd.read_csv(io.StringIO(r_ib.text))
        df_ib.columns = [c.strip().strip('"') for c in df_ib.columns]
        inbound_billnos = (set(df_ib['billNo'].dropna().astype(str).str.strip())
                           if 'billNo' in df_ib.columns else set())
        print(f"   📡 Mapping {len(inbound_billnos):,} billNo inbound")
    except Exception as e:
        print(f"   ⚠️ Không đọc được Inbound sheet: {e}")
        inbound_billnos = set()

    # Bug fix: typo 'Đã ến Hub' → 'Đã đến Hub'
    if inbound_billnos and 'billcode' in df_gsh.columns:
        df_gsh['Đã đến Hub']   = df_gsh['billcode'].astype(str).str.strip().isin(inbound_billnos).astype(int)
        df_gsh['Chưa đến Hub'] = 1 - df_gsh['Đã đến Hub']
    else:
        df_gsh['Đã đến Hub']   = 0
        df_gsh['Chưa đến Hub'] = 1

    # — Bước 5: Pivot Arrival (tích lũy) —
    try:
        # Bug fix: agg_dict an toàn — kiểm tra cột trước khi dùng
        count_col = 'billcode' if 'billcode' in df_gsh.columns else 'Đã đến Hub'
        agg_dict = {
            'Tổng số đơn':  (count_col,         'size'),
            'Đã đến Hub':   ('Đã đến Hub',   'sum'),
            'Chưa đến Hub': ('Chưa đến Hub', 'sum'),
            'Last_time_dt': ('scantime_dt',  'max'),
        }
        df_new_arr = (df_gsh
                      .groupby(['Ngày vận hành', 'Pickup_station', 'Scan Hour'])
                      .agg(**agg_dict)
                      .reset_index())
        df_new_arr['Last time'] = df_new_arr['Last_time_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_new_arr = df_new_arr.drop(columns=['Last_time_dt'])
        # Bug fix: Scan Hour nhất quán int — để upsert_arrival so sánh đúng
        df_new_arr['Scan Hour'] = df_new_arr['Scan Hour'].astype(int)

        # Ghi lên Google Sheet Arrival (upsert tích lũy)
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            SCOPES = ['https://spreadsheets.google.com/feeds',
                      'https://www.googleapis.com/auth/drive']
            sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '{}')
            sa_info = json.loads(sa_json)
            if not sa_info:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON trống")
            # Bug fix: gspread.authorize() deprecated — vẫn hoạt động nhưng dùng đúng cách
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
            gc = gspread.authorize(creds)
            # Bug fix: tự tạo sheet Arrival nếu chưa tồn tại
            try:
                arr_sheet = gc.open_by_key(SHEET_ID).worksheet('Arrival')
            except gspread.exceptions.WorksheetNotFound:
                arr_sheet = gc.open_by_key(SHEET_ID).add_worksheet('Arrival', rows=5000, cols=10)
            old_vals = arr_sheet.get_all_values()
            if len(old_vals) > 1:
                df_old_arr = pd.DataFrame(old_vals[1:], columns=old_vals[0])
                for col in ['Scan Hour', 'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub']:
                    if col in df_old_arr.columns:
                        df_old_arr[col] = pd.to_numeric(df_old_arr[col], errors='coerce').fillna(0).astype(int)
            else:
                df_old_arr = pd.DataFrame()
            df_final_arr = upsert_arrival(df_old_arr, df_new_arr)
            # Giới hạn 7 ngày
            all_dates = sorted(df_final_arr['Ngày vận hành'].unique(), reverse=True)
            df_final_arr = df_final_arr[df_final_arr['Ngày vận hành'].isin(all_dates[:7])]
            arr_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour',
                        'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub', 'Last time']
            arr_cols = [c for c in arr_cols if c in df_final_arr.columns]
            rows = [arr_cols] + df_final_arr[arr_cols].fillna('').astype(str).values.tolist()
            arr_sheet.clear()
            arr_sheet.update(range_name='A1', values=rows)
            print(f"   ✅ Sheet Arrival đã được cập nhật: {len(rows)-1} dòng (lịch sử 7 ngày)")
        except Exception as e_sh:
            print(f"   ❌ Ghi Sheet Arrival thất bại: {e_sh}")
    except Exception as e_piv:
        print(f"   ❌ Pivot Arrival lỗi: {e_piv}")

    print("🎉 GIAM SAT PHAT HANG: Hoàn thành!")


def run_realtime_sync(session, token_mgr):
    """
    Chế độ Realtime (chạy mỗi 10 phút):
    - Kéo Dispatch API: cập nhật Pickup_time mới nhất vào SQLite
    - Kéo Backlog API: cập nhật số tồn kho thực tế
    - Push Backlog sheet lên Google Sheets ngay lập tức
    - Cập nhật Inbound sheet với pickup time mới nhất
    """
    print("\n⚡ REALTIME SYNC — Backlog + Pickup Time")
    print(f"🕐 {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')} (VN)")
    print("=" * 50)

    now_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    DATE_END   = now_vn.strftime('%Y-%m-%d %H:%M:%S')
    DATE_START = (now_vn - timedelta(days=4)).strftime('%Y-%m-%d 06:00:00')

    # Load config files
    fh = load_json(os.path.join(BASE_DIR, "config", "forecastheaders.json"))
    fp = load_json(os.path.join(BASE_DIR, "config", "forecastpayload.json"))
    dh = load_json(os.path.join(BASE_DIR, "config", "dispatchheaders.json"))
    dp_payload = load_json(os.path.join(BASE_DIR, "config", "dispatchpayload.json"))
    bh = load_json(os.path.join(BASE_DIR, "config", "backlogheaders.json"))
    bp = load_json(os.path.join(BASE_DIR, "config", "backlogpayload.json"))

    token = token_mgr.get_token()
    for h in [fh, dh, bh]:
        h['authToken'] = token
        h['Authtoken'] = token

    # Load valid.csv mapping
    d_sortcode, d_buucuc, d_tuyen, d_rank = load_valid(VALID_FILE)

    # ── 1. KÉO DISPATCH: lấy Pickup_time mới nhất ──
    print("\n📦 Kéo Dispatch API...")
    dp_payload['timeStart']      = DATE_START
    dp_payload['inputTimeStart'] = DATE_START
    dp_payload['timeEnd']        = DATE_END
    dp_payload['inputTimeEnd']   = DATE_END

    try:
        r = session.post(URL_DISPATCH, headers=dh, data=dp_payload, timeout=30)
        raw = r.json()
        total_dp = int(raw.get('data', {}).get('total', 0)) if isinstance(raw.get('data'), dict) else 0
        pages = math.ceil(total_dp / 100) if total_dp > 0 else 1

        updated_pickup = 0
        conn_rt = sqlite3.connect(DB_FILE)
        c_rt = conn_rt.cursor()

        for pg in range(1, min(pages + 1, 51)):  # Tối đa 50 trang = 5000 đơn gần nhất
            try:
                token = token_mgr.get_token()
                dh['authToken'] = token
                dh['Authtoken'] = token
                dp_payload['pageNo'] = pg
                r_pg = session.post(URL_DISPATCH, headers=dh, data=dp_payload, timeout=20)
                raw_pg = r_pg.json()
                if not isinstance(raw_pg, dict):
                    continue
                records = raw_pg.get('data', {})
                if isinstance(records, dict):
                    records = records.get('records', []) or []
                for item in (records or []):
                    if not isinstance(item, dict):
                        continue
                    wb = str(item.get('waybillNo', '')).strip()
                    status_dp = str(item.get('orderStatusName', '')).strip()
                    pk = str(item.get('updateTime') or '').strip() if status_dp == 'Đã lấy hàng' else ''
                    if wb and pk and pk.lower() not in ('nan', 'none', ''):
                        c_rt.execute("""
                            UPDATE inventory
                            SET Pickup_time = ?, status_order = ?, last_updated = CURRENT_TIMESTAMP
                            WHERE waybillNo = ? AND (Pickup_time = '' OR Pickup_time IS NULL)
                        """, (pk, status_dp, wb))
                        updated_pickup += c_rt.rowcount
            except Exception:
                continue

        conn_rt.commit()
        print(f"   ✅ Cập nhật Pickup_time cho {updated_pickup:,} đơn mới từ Dispatch API")

        # ── 2. KÉO BACKLOG: cập nhật số tồn kho thực ──
        print("\n🏭 Kéo Backlog API...")
        bp['pageNo'] = 1
        bp['pageSize'] = 500
        r_bl = session.post(URL_BACKLOG, headers=bh, data=bp, timeout=30)
        raw_bl = r_bl.json()
        if not isinstance(raw_bl, dict):
            print("   ⚠️ Backlog API trả về lỗi, bỏ qua.")
        else:
            total_bl = int(raw_bl.get('data', {}).get('total', 0)) if isinstance(raw_bl.get('data'), dict) else 0
            bl_pages = math.ceil(total_bl / 500) if total_bl > 0 else 1
            all_bl = []
            for pg_bl in range(1, bl_pages + 1):
                try:
                    token = token_mgr.get_token()
                    bh['authToken'] = token
                    bh['Authtoken'] = token
                    bp['pageNo'] = pg_bl
                    r_b = session.post(URL_BACKLOG, headers=bh, data=bp, timeout=20)
                    raw_b = r_b.json()
                    if not isinstance(raw_b, dict):
                        continue
                    recs = raw_b.get('data', {})
                    if isinstance(recs, dict):
                        recs = recs.get('records', []) or []
                    all_bl.extend(recs or [])
                except Exception:
                    continue

            print(f"   ✅ Backlog API: {len(all_bl):,} đơn thực tế trong kho HUB")

            # Cleanup stale records trong DB
            if all_bl:
                live_wbs = {str(r.get('billcode', '')).strip() for r in all_bl if isinstance(r, dict)}
                c_rt.execute("SELECT waybillNo FROM inventory WHERE status_order = 'Đang trên bãi'")
                db_wbs = {row[0] for row in c_rt.fetchall()}
                stale = db_wbs - live_wbs
                if stale:
                    c_rt.executemany(
                        "UPDATE inventory SET status_order = 'Đã rời HUB', last_updated = CURRENT_TIMESTAMP WHERE waybillNo = ?",
                        [(w,) for w in stale]
                    )
                    conn_rt.commit()
                    print(f"   ✅ Dọn dẹp {len(stale):,} đơn stale → 'Đã rời HUB'")

            # Push Backlog sheet
            BACKLOG_REDELIVER = {
                'Người nhận từ chối nhận hàng','Khách không ở địa chỉ giao hàng',
                'Số điện thoại không liên lạc được','Người nhận đặt trùng đơn / mua nhầm',
                'Khách từ chối thanh toán','Khách không đặt hàng','Sai số điện thoại',
                'Khách yêu cầu dùng thử, kiểm hàng','Người nhận hẹn lại thời gian giao hàng',
                'Địa chỉ khách hàng sai','Hàng hóa hư hỏng một phần','Hàng hóa hư hỏng hoàn toàn'
            }
            backlog_by_station = {}
            for item in all_bl:
                if not isinstance(item, dict):
                    continue
                if item.get('operate_site_type') not in ('Trong kho', None, ''):
                    if item.get('operate_site_type') != 'Trong kho':
                        continue
                dest = str(item.get('destination_site_name', '')).strip()
                src  = str(item.get('take_site_name', '')).strip()
                remark = str(item.get('abnormal_remark', '')).strip()
                station_raw = src if remark in BACKLOG_REDELIVER else dest
                station = d_buucuc.get(station_raw, station_raw).upper()
                wt = float(str(item.get('weight', 0)).replace(',', '') or 0)
                if station not in backlog_by_station:
                    backlog_by_station[station] = {'volume': 0, 'weight': 0.0}
                backlog_by_station[station]['volume'] += 1
                backlog_by_station[station]['weight'] += wt

            # Ghi lên Google Sheets
            try:
                creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
                local_creds = r"C:\Users\lehoa\OneDrive\Desktop\testing\addressproject.json"
                if not creds_json and os.path.exists(local_creds):
                    with open(local_creds, 'r', encoding='utf-8') as f:
                        creds_json = f.read()
                if creds_json:
                    import gspread
                    from google.oauth2.service_account import Credentials
                    creds_info = json.loads(creds_json)
                    creds = Credentials.from_service_account_info(creds_info, scopes=[
                        'https://spreadsheets.google.com/feeds',
                        'https://www.googleapis.com/auth/drive'
                    ])
                    gc = gspread.authorize(creds)

                    # Load master_chutes từ Sheet
                    master_chutes = {}
                    try:
                        ss = gc.open_by_key(SHEET_ID)
                        sheet1 = ss.worksheet("Sheet1")
                        all_rows = sheet1.get_all_values()
                        if len(all_rows) > 1:
                            hdrs = all_rows[0]
                            ci_zone = hdrs.index("Zone") if "Zone" in hdrs else 0
                            ci_area = hdrs.index("AreaID") if "AreaID" in hdrs else 1
                            ci_name = hdrs.index("Bưu cục") if "Bưu cục" in hdrs else 2
                            ci_cap  = hdrs.index("Sức chứa") if "Sức chứa" in hdrs else 6
                            for row in all_rows[1:]:
                                if len(row) > max(ci_zone, ci_area, ci_name):
                                    z, a, n = row[ci_zone].strip(), row[ci_area].strip(), row[ci_name].strip()
                                    if z and a and n:
                                        master_chutes[(z, a)] = {"zone": z, "area_id": a, "name": n,
                                                                  "capacity": row[ci_cap] if ci_cap < len(row) else "780"}
                    except Exception:
                        pass

                    current_date_str = now_vn.strftime('%Y-%m-%d')
                    update_backlog_sheet(gc, master_chutes, backlog_by_station, current_date_str)
                    print(f"   ✅ Đã push Backlog sheet lên Google Sheets ({len(all_bl):,} đơn)")
            except Exception as e_gs:
                print(f"   ⚠️ Lỗi push Google Sheets: {e_gs}")

        conn_rt.close()
    except Exception as e_rt:
        print(f"   ❌ Lỗi Realtime sync: {e_rt}")

    print("\n✅ REALTIME SYNC hoàn thành!")


def main():

    parser = argparse.ArgumentParser(description="J&T Cargo HCM HUB — Unified Sync + Giam sat phat hang")
    parser.add_argument("--rebuild", type=int, help="Rebuild data for the last N operating days")
    parser.add_argument("--gsh-only", action="store_true", help="Chỉ chạy Giam sat phat hang")
    parser.add_argument("--sync-only", action="store_true", help="Chỉ chạy Inventory sync")
    args = parser.parse_args()

    session   = build_session()
    token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)

    # Chạy song song cả hai pipeline trên cùng 1 session / token
    tasks = []
    if not args.gsh_only:
        tasks.append(("InventorySync", lambda: run_once(session, token_mgr, rebuild_days=args.rebuild)))
    # Bỏ qua GiamSatPhatHang cũ vì InventorySync đã tự động xử lý và lưu Arrival vào data/arrival.json
    # if not args.sync_only:
    #     tasks.append(("GiamSatPhatHang", lambda: run_giam_sat_phat_hang(session, token_mgr)))

    if len(tasks) == 1:
        # Chạy đơn
        name, fn = tasks[0]
        try:
            fn()
        except Exception as e:
            print(f"\n❌ Lỗi [{name}]: {e}")
            sys.exit(1)
    else:
        # Chạy song song — cả hai pipeline cùng lúc
        print("\n🚀 Chạy song song: InventorySync + GiamSatPhatHang...")
        errors = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            future_map = {ex.submit(fn): name for name, fn in tasks}
            for fut in as_completed(future_map):
                name = future_map[fut]
                try:
                    fut.result()
                    print(f"   ✅ [{name}] Hoàn thành")
                except Exception as e:
                    print(f"   ❌ [{name}] Lỗi: {e}")
                    errors.append(name)
        if errors:
            print(f"\n⚠️ Có lỗi trong: {', '.join(errors)}")
            sys.exit(1)

    # Mirror data/ files to root data/ and src/data/ for frontend and GitHub raw access
    try:
        import shutil
        for dest_dir in [os.path.join("..", "data"), os.path.join("..", "src", "data")]:
            os.makedirs(dest_dir, exist_ok=True)
            if os.path.exists("data"):
                for fn in os.listdir("data"):
                    if fn.endswith(".json") or fn.endswith(".gz"):
                        shutil.copy2(os.path.join("data", fn), os.path.join(dest_dir, fn))
        print("   📂 Đã đồng bộ tất cả file JSON ra thư mục gốc '../data/' và '../src/data/'.")
    except Exception as e_mir:
        print(f"   ⚠️ Lỗi mirror data: {e_mir}")


if __name__ == "__main__":
    main()