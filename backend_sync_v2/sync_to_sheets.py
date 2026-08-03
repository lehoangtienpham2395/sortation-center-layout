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
PASSWORD   = os.environ.get("SYSTEM_PASSWORD", "").strip() or 'Tien@giang0203'
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

RETRYABLE_STATUS = {405, 429, 500, 502, 503, 504}

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
    if not dt_str:
        return ""
    s = str(dt_str).strip()
    if s.lower() in ('nan', 'none', 'n/a', 'null', 'nat', ''):
        return ""
    if len(s) >= 13 and s[4] == '-' and s[7] == '-':
        try:
            yr = int(s[:4])
            mo = int(s[5:7])
            dy = int(s[8:10])
            hr = int(s[11:13])
            if hr < 6:
                dt = datetime(yr, mo, dy) - timedelta(days=1)
                return dt.strftime('%Y-%m-%d')
            return s[:10]
        except Exception:
            pass
    try:
        dt = pd.to_datetime(s)
        if pd.isna(dt):
            return ""
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
    
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = OFF")
    c.execute("PRAGMA cache_size = -64000")
    c.execute("PRAGMA temp_store = MEMORY")
    c.execute("PRAGMA count_changes = OFF")
    
    # Auto-migrate legacy table if waybillNo column exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shipments'")
    if c.fetchone():
        c.execute("PRAGMA table_info(shipments)")
        col_list = [col[1] for col in c.fetchall()]
        if 'waybillNo' in col_list:
            print("   📦 Phát hiện bảng 'shipments' legacy (22 cột). Bắt đầu nâng cấp tự động sang Schema Enterprise v2.0 (29 cột)...")
            try:
                c.execute("DROP TABLE IF EXISTS shipments_legacy")
                c.execute("ALTER TABLE shipments RENAME TO shipments_legacy")
                conn.commit()
            except Exception as e_ren:
                print(f"   ⚠️ Lỗi rename legacy shipments: {e_ren}")

    c.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            tracking TEXT PRIMARY KEY,
            data_source TEXT,
            Orders_weight REAL,
            Pickup_station TEXT,
            Dispatch_code TEXT,
            Pickup_time TEXT,
            Pickup_ontime TEXT,
            Created_time TEXT,
            Next_station TEXT,
            Round TEXT,
            Rank TEXT,
            inbound_scanDate TEXT,
            outbound_scanDate TEXT,
            arrival_scanDate TEXT,
            dispatch_actual TEXT,
            status_sys TEXT,
            time_ref TEXT,
            is_backlog INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            trip_code TEXT DEFAULT '',
            transporing_time TEXT DEFAULT '',
            transported_time TEXT DEFAULT '',
            Orders_num INTEGER DEFAULT 1,
            Pickup_station2 TEXT DEFAULT '',
            AreaCode TEXT DEFAULT '',
            flowTypeDesc TEXT DEFAULT '',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            last_retry_time TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_created ON shipments(Created_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_status ON shipments(status_sys)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_active ON shipments(is_active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_inbound ON shipments(inbound_scanDate)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ship_outbound ON shipments(outbound_scanDate)")
    conn.commit()

    # If legacy table exists, copy records over
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shipments_legacy'")
    if c.fetchone():
        try:
            c.execute("""
                INSERT OR IGNORE INTO shipments (
                    tracking, data_source, Orders_weight, Pickup_station, Dispatch_code,
                    Pickup_time, Pickup_ontime, Created_time, Next_station, Round, Rank,
                    inbound_scanDate, outbound_scanDate, arrival_scanDate, dispatch_actual,
                    status_sys, time_ref, is_backlog, is_active, last_updated
                )
                SELECT 
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, dispatchNetworkTime, next_station, Tuyến, Rank,
                    inbound_scanDate, outbound_scanDate, Arrival_time, dispatch_actual,
                    status_order, time_ref, is_backlog, is_active, last_updated
                FROM shipments_legacy
            """)
            c.execute("DROP TABLE shipments_legacy")
            conn.commit()
            print("   ✅ Migrate dữ liệu legacy sang Enterprise v2.0 thành công!")
        except Exception as e_mig:
            print(f"   ⚠️ Lỗi migrate legacy shipments: {e_mig}")

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
        headers['Authtoken'] = token
        try:
            r = session.post(url, params=params, headers=headers,
                             json=json_body, data=data, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            time.sleep(BACKOFF_BASE * attempt)
            continue

        if (r.status_code == 401 or r.status_code == 405) and not refreshed:
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
        if (r.status_code == 401 or r.status_code == 405) and not refreshed:
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
            time.sleep((p % 4) * 0.25)  # Tránh gửi nhiều request cùng 1 miligiây
            return fetch_page(p)
        except Exception as e:
            print(f"      ⚠️ Lỗi tải trang {p}: {e}")
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

    # 2. Đọc mapping sortcode từ valid.csv cục bộ (Hỗ trợ linh hoạt cấu trúc cột)
    d_sortcode = {}
    try:
        valid_paths = [
            VALID_FILE,
            os.path.join(BASE_DIR, "config", "valid.csv"),
            r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv",
            os.path.join(BASE_DIR, "Exportauto", "Valid", "valid.csv")
        ]
        valid_file_to_use = next((p for p in valid_paths if os.path.exists(p)), VALID_FILE)
        if os.path.exists(valid_file_to_use):
            df_v = pd.read_csv(valid_file_to_use, encoding='utf-8-sig', dtype=str)
            df_v.columns = df_v.columns.str.strip()
            if 'sortcode' in df_v.columns:
                for _, row in df_v.iterrows():
                    sc = str(row.get('sortcode', '')).strip()
                    if sc and not any(x in sc.lower() for x in ('offline', 'nan', 'none')):
                        for col in ['Station_1', 'Station_2', 'Bưu cục', 'Buu cuc', 'Bưu cục final', 'Buu cuc final']:
                            if col in df_v.columns and pd.notna(row.get(col)):
                                st_name = str(row[col]).strip().upper()
                                if st_name and st_name not in ('NAN', 'NONE', ''):
                                    d_sortcode[st_name] = sc
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
        valid_paths = [
            path,
            os.path.join(BASE_DIR, "config", "valid.csv"),
            r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv",
            os.path.join(BASE_DIR, "Exportauto", "Valid", "valid.csv")
        ]
        valid_file_to_use = next((p for p in valid_paths if os.path.exists(p)), path)
        df = pd.read_csv(valid_file_to_use, encoding='utf-8-sig', dtype=str)
        df.columns = df.columns.str.strip()
        print(f"   ✅ Valid: {len(df)} dòng | Cột: {list(df.columns)}")
        d_sortcode, d_buucuc, d_tuyen, d_rank = {}, {}, {}, {}

        bc_col = next((c for c in ['Station_2', 'Station_1', 'Bưu cục final', 'Buu cuc final', 'Bưu cục', 'Buu cuc'] if c in df.columns), None)
        sc_col = 'sortcode' if 'sortcode' in df.columns else None
        rd_col = next((c for c in ['Round', 'Tuyến', 'Tuyen'] if c in df.columns), None)
        rk_col = 'Rank' if 'Rank' in df.columns else None

        if sc_col and bc_col:
            for _, row in df.iterrows():
                sc = str(row.get(sc_col, '')).strip()
                bc = str(row.get(bc_col, '')).strip()
                if sc and bc and sc.lower() not in ('nan', 'none') and bc.lower() not in ('nan', 'none'):
                    d_sortcode[sc] = bc

        if bc_col:
            for col_name in ['Station_1', 'Station_2', 'Bưu cục', 'Buu cuc']:
                if col_name in df.columns:
                    for _, row in df.iterrows():
                        st = str(row.get(col_name, '')).strip()
                        bc = str(row.get(bc_col, '')).strip()
                        if st and bc and st.lower() not in ('nan', 'none') and bc.lower() not in ('nan', 'none'):
                            d_buucuc[st] = bc

            if rd_col:
                for _, row in df.iterrows():
                    bc = str(row.get(bc_col, '')).strip()
                    rd = str(row.get(rd_col, '')).strip()
                    if bc and rd:
                        d_tuyen[bc] = rd
                        if 'Station_1' in df.columns:
                            d_tuyen[str(row.get('Station_1', '')).strip()] = rd

            if rk_col:
                for _, row in df.iterrows():
                    bc = str(row.get(bc_col, '')).strip()
                    rk = str(row.get(rk_col, '')).strip()
                    if bc and rk:
                        d_rank[bc] = rk
                        if 'Station_1' in df.columns:
                            d_rank[str(row.get('Station_1', '')).strip()] = rk

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


def export_heatmap_json():
    print("\n📊 Bắt đầu tính toán và xuất dữ liệu Heatmap...")
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(
            """SELECT dispatchNetworkTime, Pickup_time, Arrival_time, inbound_scanDate, outbound_scanDate 
               FROM shipments""",
            conn
        )
        conn.close()

        if df.empty:
            print("   ⚠️ Không có dữ liệu trong shipments để tính Heatmap.")
            return

        # Helper to parse datetime
        for col in ['dispatchNetworkTime', 'Pickup_time', 'Arrival_time', 'inbound_scanDate', 'outbound_scanDate']:
            df[col + '_dt'] = pd.to_datetime(df[col], errors='coerce')

        # Day names list
        DAYS_ENG = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        # We want to find all unique operating dates >= 2026-07-05
        all_op_dates = set()
        for col in ['dispatchNetworkTime_dt', 'Pickup_time_dt', 'Arrival_time_dt', 'inbound_scanDate_dt', 'outbound_scanDate_dt']:
            dates = df[col].dropna()
            for dt in dates:
                if dt.hour < 6:
                    op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    op_date = dt.strftime('%Y-%m-%d')
                if op_date >= '2026-07-05':
                    all_op_dates.add(op_date)

        sorted_op_dates = sorted(list(all_op_dates), reverse=True)

        # Initialize grid: unique_dates x 24 hours
        grid = {}
        for op_date in sorted_op_dates:
            dt_obj = pd.to_datetime(op_date)
            day_name = DAYS_ENG[dt_obj.weekday()]
            for hr in range(24):
                grid[(op_date, hr)] = {
                    'date': op_date,
                    'dayName': day_name,
                    'hour': hr,
                    'created': 0,
                    'pickup': 0,
                    'transporting': 0,
                    'inbound': 0,
                    'outbound': 0
                }

        # Populate grid
        # Created (dispatchNetworkTime)
        df_fc = df[df['dispatchNetworkTime_dt'].notna()]
        for dt in df_fc['dispatchNetworkTime_dt']:
            if dt.hour < 6:
                op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                op_date = dt.strftime('%Y-%m-%d')
            if (op_date, dt.hour) in grid:
                grid[(op_date, dt.hour)]['created'] += 1

        # Pickup Done (Pickup_time)
        df_pk = df[df['Pickup_time_dt'].notna()]
        for dt in df_pk['Pickup_time_dt']:
            if dt.hour < 6:
                op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                op_date = dt.strftime('%Y-%m-%d')
            if (op_date, dt.hour) in grid:
                grid[(op_date, dt.hour)]['pickup'] += 1

        # Transporting (Arrival_time)
        df_arr = df[df['Arrival_time_dt'].notna()]
        for dt in df_arr['Arrival_time_dt']:
            if dt.hour < 6:
                op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                op_date = dt.strftime('%Y-%m-%d')
            if (op_date, dt.hour) in grid:
                grid[(op_date, dt.hour)]['transporting'] += 1

        # Inbound (inbound_scanDate)
        df_ib = df[df['inbound_scanDate_dt'].notna()]
        for dt in df_ib['inbound_scanDate_dt']:
            if dt.hour < 6:
                op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                op_date = dt.strftime('%Y-%m-%d')
            if (op_date, dt.hour) in grid:
                grid[(op_date, dt.hour)]['inbound'] += 1

        # Outbound (outbound_scanDate)
        df_ob = df[df['outbound_scanDate_dt'].notna()]
        for dt in df_ob['outbound_scanDate_dt']:
            if dt.hour < 6:
                op_date = (dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                op_date = dt.strftime('%Y-%m-%d')
            if (op_date, dt.hour) in grid:
                grid[(op_date, dt.hour)]['outbound'] += 1

        heatmap_data = list(grid.values())

        os.makedirs("data", exist_ok=True)
        with open("data/heatmap.json", "w", encoding="utf-8") as f:
            json.dump(heatmap_data, f, ensure_ascii=False, indent=2)
        print(f"   💾 Đã xuất file 'data/heatmap.json' với {len(heatmap_data)} dòng.")
    except Exception as e_heat:
        print(f"   ⚠️ Lỗi xuất dữ liệu Heatmap: {e_heat}")


def update_inbound_sheets(ss, results, master_chutes, d_buucuc):
    print("\n📥 Bắt đầu cập nhật dữ liệu Inbound gom nhóm theo trạng thái & khùng giờ lên Google Sheets...")
    
    def safe_hour_format(val):
        if not val or str(val).strip().lower() in ('nan', 'none', 'nat', 'n/a', 'backlog', ''):
            return ""
        val_str = str(val).strip()
        if len(val_str) >= 13 and val_str[4] == '-' and val_str[7] == '-':
            return val_str[:13] + ':00'
        try:
            dt = pd.to_datetime(val_str)
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
        # ✅ GUARD: Chỉ lấy đơn is_active=1 (đang sống).
        # Không dùng OR override vì sẽ kéo vào cả đơn đã rời HUB/đã kết (is_active=0)
        # khiến Forecast bị phình lên sai số.
        # Đơn lịch sử (đã inbound) vẫn được giữ qua cột inbound_scanDate >= cutoff.
        from datetime import timedelta as _td
        _cutoff = (datetime.now() - _td(days=5)).strftime('%Y-%m-%d')  # dynamic, không hardcode
        df_ship = pd.read_sql_query(f"""
            SELECT pickNetworkName, status_order, weight, 
                   inbound_scanDate, dispatchNetworkTime, Pickup_time, Arrival_time, inbound_network
            FROM shipments
            WHERE is_active = 1
               OR (inbound_scanDate != '' AND inbound_scanDate >= '{_cutoff}')
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

            current_status = row.get('status_order', '')

            # ✅ Fix: Đơn "Đã rời HUB" có inbound_scanDate vẫn phải được
            # tính vào Inbound để báo cáo lịch sử đúng.
            # Chỉ skip nếu chưa có inbound_scanDate (đơn chưa vào HUB bao giờ).
            if current_status == 'Đã rời HUB':
                if ib_time:
                    # Đã qua HUB rồi ra → vẫn tính là Inbound
                    status = 'Inbound'
                else:
                    # Chưa từng inbound → bỏ qua
                    continue
            else:
                status = status_map.get(current_status, 'Created')

                
            op_date_ib = get_operating_date(ib_time) if ib_time else ""
            op_date_fc = get_operating_date(fc_time) if fc_time else ""
            op_date_pk = get_operating_date(pk_time) if pk_time else ""
            op_date_arr = get_operating_date(arr_time) if arr_time else ""
            
            # Apply +36 hours shift for northern shipments in inbound.json
            if status == 'Inbound':
                pkn = (row.get('inbound_network') or '').strip()
            else:
                pkn = (row.get('pickNetworkName') or row.get('inbound_network') or '').strip()
            pkn_upper = pkn.upper()
            NORTH_POST_OFFICES = {
                'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
                'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
                'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
                'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
                'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
                'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
                'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
            }
            is_north = (
                pkn_upper.startswith('HN ') or 
                pkn_upper.startswith('HD ') or 
                pkn_upper.startswith('HY ') or 
                pkn_upper == 'BN HUB' or
                pkn_upper in NORTH_POST_OFFICES
            )
            if is_north and not ib_time and arr_time:
                try:
                    arr_dt = pd.to_datetime(arr_time)
                    shifted_arr_dt = arr_dt + pd.Timedelta(hours=36)
                    op_date_arr = shifted_arr_dt.strftime('%Y-%m-%d')
                    arr_hour = shifted_arr_dt.strftime('%Y-%m-%d %H:00')
                except Exception:
                    pass

            # Calculate Drop Type
            if op_date_fc:
                if op_date_pk:
                    loai_rot = "Rớt hôm nay" if op_date_fc == op_date_pk else "Rớt hôm trước"
                else:
                    loai_rot = "Rớt hôm trước" if op_date_fc < current_op_date else "Rớt hôm nay"
            else:
                loai_rot = "Rớt hôm nay"

            ib_hour = safe_hour_format(ib_time)
            fc_hour = safe_hour_format(fc_time)
            pk_hour = safe_hour_format(pk_time)
            arr_hour = safe_hour_format(arr_time)

            unique_rows.append({
                'Bưu cục': 'BN HUB' if is_north else pkn,
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

        # Preserve original Forecast operating dates so historical reports remain exact
        projected_rows = unique_rows

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
            drop_type_code = 'rot_today' if loai_rot == 'Rớt hôm nay' else ('rot_yesterday' if loai_rot == 'Rớt hôm trước' else '')
            final_rows.append({
                'station_name': fc_name,
                'status': status,
                'volume': stats['volume'],
                'weight_ton': round(stats['weight'] / 1000.0, 4),
                'op_date_inbound': op_ib,
                'op_date_forecast': op_fc,
                'op_date_pickup': op_pk,
                'op_date_arrival': op_arr,
                'inbound_hour': ib_hour,
                'created_hour': fc_hour,
                'pickup_hour': pk_hour,
                'arrival_hour': arr_hour,
                'drop_type': drop_type_code,
                
                # Legacy aliases
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

    # ================================================================
    # ✅ SANITY GUARD: Kiểm tra Forecast tổng bất thường trước khi ghi
    # Nếu Forecast thay đổi > 30% so với lần trước → log cảnh báo rõ ràng
    # ================================================================
    if not df_inbound_aggregated.empty:
        fc_total_now = len(df_inbound_aggregated[
            df_inbound_aggregated['Trạng thái'].isin(['Created'])
            & (df_inbound_aggregated['Ngày vận hành_Forecast'] != '')
        ])
        # Đọc giá trị Forecast lần trước từ DB meta (nếu có)
        try:
            _meta_conn = sqlite3.connect(DB_FILE)
            _meta = _meta_conn.execute("SELECT value FROM meta WHERE key='last_forecast_total'").fetchone()
            _meta_conn.close()
            if _meta:
                fc_prev = int(_meta[0])
                if fc_prev > 100:  # Chỉ áp dụng khi số lượng đáng kể để tránh lỗi chia nhỏ
                    pct_change = abs(fc_total_now - fc_prev) / fc_prev
                    if pct_change > 3.0:  # Thay đổi đột biến quá 300% (3.0)
                        print(f"\n{'🚨'*20}")
                        print(f"   🚨 ERROR: PHÁT HIỆN FORECAST ĐỘT BIẾN QUÁ MỨC CHO PHÉP!")
                        print(f"   🚨 Lần trước: {fc_prev:,}  |  Lần này: {fc_total_now:,}  |  Thay đổi: {pct_change:.0%}")
                        print(f"   🚨 BẢO VỆ AN TOÀN: Dừng khẩn cấp tiến trình sync để tránh ghi đè dữ liệu hỏng!")
                        print(f"{'🚨'*20}\n")
                        raise ValueError(f"Forecast đột biến {pct_change:.0%}, dừng tiến trình để bảo vệ DB.")
                    elif pct_change > 0.30:
                        print(f"\n{'='*60}")
                        print(f"   ⚠️  CẢNH BÁO: Forecast thay đổi bất thường!")
                        print(f"   ⚠️  Lần trước: {fc_prev:,}  |  Lần này: {fc_total_now:,}  |  Thay đổi: {pct_change:.0%}")
                        print(f"   ⚠️  Kiểm tra lại: date range, is_active filter, dedup logic!")
                        print(f"{'='*60}\n")
        except ValueError as ve:
            raise ve
        except Exception:
            pass
        # Ghi lại giá trị hiện tại vào meta để so sánh lần sau
        try:
            _meta_conn = sqlite3.connect(DB_FILE)
            _meta_conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            _meta_conn.execute("INSERT OR REPLACE INTO meta VALUES ('last_forecast_total', ?)", (str(fc_total_now),))
            _meta_conn.commit()
            _meta_conn.close()
        except Exception:
            pass

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

    # 5. Arrival sheet (giám sát hàng đến trung chuyển – tích lũy theo ngày, trạm, xe)
    print("\n📋 Xử lý sheet Arrival...")
    df_enriched = pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_FILE)
        df_sqlite_active = pd.read_sql_query("""
            SELECT pickNetworkName as last_dept_name, 
                   waybillNo as billcode, 
                   CAST(weight AS FLOAT) as package_charge_weight, 
                   dispatchNetworkTime as scantime,
                   Pickup_time as gio_di_thuc_te,
                   inbound_network, status_order
            FROM shipments 
            WHERE is_active = 1 AND status_order = 'Đang trên đường'
        """, conn)
        conn.close()
        if not df_sqlite_active.empty:
            df_enriched = df_sqlite_active
    except Exception as e_sq:
        print(f"   ⚠️ SQLite active query note: {e_sq}")

    arrival_raw = results.get('arrival', [])
    if arrival_raw:
        df_arrival_api = pd.DataFrame(arrival_raw)
        if 'last_dept_name' not in df_arrival_api.columns:
            for col in ['scansitename', 'Pickup_station', 'sendSite', 'sendSiteName', 'startSiteName', 'bưu_cục_gửi']:
                if col in df_arrival_api.columns:
                    df_arrival_api['last_dept_name'] = df_arrival_api[col]
                    break
        if df_enriched.empty:
            df_enriched = df_arrival_api
        if 'last_dept_name' not in df_enriched.columns:
            df_enriched['last_dept_name'] = ''

        if 'transfercode' not in df_enriched.columns:
            for col in ['traceCode', 'vehicleNo', 'carNo', 'licensePlate', 'truckCode', 'mã_chuyến']:
                if col in df_enriched.columns:
                    df_enriched['transfercode'] = df_enriched[col]
                    break
        if 'transfercode' not in df_enriched.columns:
            df_enriched['transfercode'] = ''

        # 5. Tính toán ETA Incoming từ file etatrucking.csv
        eta_dict = {}
        # Hỗ trợ cả 2 môi trường (local Desktop và workspace GHA)
        eta_paths = [
            os.path.join(BASE_DIR, "Exportauto", "Valid", "etatrucking.csv"),
            os.path.join(BASE_DIR, "config", "etatrucking.csv"),
            os.path.join(os.path.dirname(BASE_DIR), "backend_sync", "Exportauto", "Valid", "etatrucking.csv"),
            os.path.join(BASE_DIR, "backend_sync", "Exportauto", "Valid", "etatrucking.csv")
        ]
        eta_file = None
        for p in eta_paths:
            if os.path.exists(p):
                eta_file = p
                break
                
        if eta_file:
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
            except Exception as e_eta:
                print(f"   ⚠️ Lỗi đọc etatrucking.csv: {e_eta}")

        col_eta_incoming = []
        for _, row in df_enriched.iterrows():
            st = str(row.get('last_dept_name') or '').strip().upper()
            scan_t = str(row.get('gio_di_thuc_te') or row.get('Pickup_time') or '').strip()
            
            eta_hours = eta_dict.get(st)
            if eta_hours is not None and scan_t and scan_t.lower() not in ('nan', 'none', ''):
                try:
                    dt_scan = pd.to_datetime(scan_t, errors='coerce')
                    if pd.notna(dt_scan):
                        dt_eta = dt_scan + timedelta(hours=eta_hours)
                        col_eta_incoming.append(dt_eta.strftime('%Y-%m-%d %H:%M:%S'))
                    else:
                        col_eta_incoming.append('')
                except Exception:
                    col_eta_incoming.append('')
            else:
                col_eta_incoming.append('')
                
        df_enriched['ETA Incoming'] = col_eta_incoming

        if 'billcode' not in df_enriched.columns:
            for col in ['waybillNo', 'billNo', 'waybill_no']:
                if col in df_enriched.columns:
                    df_enriched['billcode'] = df_enriched[col]
                    break
        if 'billcode' not in df_enriched.columns:
            df_enriched['billcode'] = ''
            
        if 'package_charge_weight' not in df_enriched.columns:
            df_enriched['package_charge_weight'] = 0
            
    # Populate df_enriched from SQLite active on-the-road shipments (status_order == 'Đang trên đường')
    from zoneinfo import ZoneInfo
    now_vn_eta = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    today_op_date = get_operating_date(now_vn_eta.strftime('%Y-%m-%d %H:%M:%S'))

    try:
        conn = sqlite3.connect(DB_FILE)
        df_sqlite_active = pd.read_sql_query("""
            SELECT pickNetworkName as last_dept_name, 
                   waybillNo as billcode, 
                   CAST(weight AS FLOAT) as package_charge_weight, 
                   dispatchNetworkTime as scantime,
                   Pickup_time as gio_di_thuc_te,
                   inbound_network, status_order,
                   dispatch_plan as transfercode
            FROM shipments 
            WHERE is_active = 1 AND status_order IN ('Đang trên đường', 'Đã lấy hàng')
        """, conn)
        conn.close()
        if not df_sqlite_active.empty:
            df_sqlite_active['ETA Incoming'] = df_sqlite_active['gio_di_thuc_te']
            df_sqlite_active['Ngày vận hành'] = today_op_date
            df_enriched = df_sqlite_active
    except Exception as e_sq:
        print(f"   ⚠️ SQLite active query note: {e_sq}")
            
    if not df_enriched.empty:
        try:
            # Tải cấu trúc phân hạng d_rank từ file valid.csv
            _, _, _, d_rank = load_valid(VALID_FILE)
            
            # Xử lý kiểu dữ liệu số & Rank cho df_enriched
            df_enriched['package_charge_weight'] = pd.to_numeric(df_enriched['package_charge_weight'], errors='coerce').fillna(0)
            
            # Xác định Rank cho từng dòng
            def get_arrival_rank(row):
                nguon = str(row.get('nguon_anh_xa', '')).strip().lower()
                station = str(row.get('last_dept_name', '')).strip().upper()
                if station == 'BN HUB' or nguon == 'linehaul':
                    return 'Linehaul'
                mapped_rank = d_rank.get(station, '')
                if mapped_rank == 'BN HUB':
                    return 'Linehaul'
                return 'Shuttle'
                
            df_enriched['Rank'] = df_enriched.apply(get_arrival_rank, axis=1)

            # 1. TẠO DATASET A: QUÉT LỊCH SỬ ĐỂ XEM TREND (DÀNH CHO BIỂU ĐỒ HOURLY PROCESSING TREND)
            df_arr = df_enriched.copy()
            # Lấy scantime từ các trường thời gian khả dụng của df_enriched theo thứ tự ưu tiên (ưu tiên giờ DỠ HÀNG tại HUB)
            df_arr['scantime_dt'] = pd.to_datetime(df_arr.get('unloadingStartTime'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('unloadingEndTime'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('arrival_time'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('ETA Incoming'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('gio_di_thuc_te'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('gio_bat_dau_xep'), errors='coerce')
            df_arr.loc[df_arr['scantime_dt'].isna(), 'scantime_dt'] = pd.to_datetime(df_arr.get('scantime'), errors='coerce')
            
            df_arr['Scan Hour'] = df_arr['scantime_dt'].dt.strftime('%Y-%m-%d %H:00').fillna('')
            
            # Tính Đã đến Hub / Chưa đến Hub
            if 'arrival_time' not in df_arr.columns:
                df_arr['arrival_time'] = df_arr.get('unloadingStartTime')
            
            arr_series = df_arr['arrival_time'].fillna('').astype(str).str.strip().str.lower() if 'arrival_time' in df_arr.columns else pd.Series([''] * len(df_arr))
            df_arr['Đã đến Hub'] = (arr_series != '') & (arr_series != 'nan') & (arr_series != 'none')
            df_arr['Đã đến Hub'] = df_arr['Đã đến Hub'].astype(int)
            df_arr['Chưa đến Hub'] = 1 - df_arr['Đã đến Hub']
            
            # Groupby theo Ngày vận hành, Pickup_station (last_dept_name), Scan Hour
            df_pivot_arr = (df_arr.groupby(['Ngày vận hành', 'last_dept_name', 'Scan Hour'])
                            .agg(
                                Tong_don=('billcode', 'count'),
                                Da_den=('Đã đến Hub', 'sum'),
                                Chua_den=('Chưa đến Hub', 'sum'),
                                Last_time_dt=('scantime_dt', 'max')
                            ).reset_index())
            
            df_pivot_arr.rename(columns={
                'last_dept_name': 'Pickup_station',
                'Tong_don': 'Tổng số đơn',
                'Da_den': 'Đã đến Hub',
                'Chua_den': 'Chưa đến Hub'
            }, inplace=True)
            
            df_pivot_arr['Last time'] = df_pivot_arr['Last_time_dt'].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')
            df_pivot_arr = df_pivot_arr.drop(columns=['Last_time_dt'])
            
            # Lưu lịch sử 7 ngày cho arrival.json
            arrival_cols = ['Ngày vận hành', 'Pickup_station', 'Scan Hour', 'Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub', 'Last time']
            
            df_old_arr = pd.DataFrame()
            arrival_json_path = "data/arrival.json"
            if os.path.exists(arrival_json_path):
                try:
                    df_old_arr = pd.read_json(arrival_json_path)
                except Exception:
                    pass
            
            if df_old_arr.empty and not DISABLE_GOOGLE_SHEETS and ss:
                try:
                    arr_sheet = ss.worksheet('Arrival')
                    old_vals = arr_sheet.get_all_values()
                    if len(old_vals) > 1:
                        df_old_arr = pd.DataFrame(old_vals[1:], columns=old_vals[0])
                except Exception:
                    pass
            
            if not df_old_arr.empty and not all(c in df_old_arr.columns for c in arrival_cols):
                df_old_arr = pd.DataFrame()
                
            if not df_old_arr.empty:
                for col in ['Tổng số đơn', 'Đã đến Hub', 'Chưa đến Hub']:
                    if col in df_old_arr.columns:
                        df_old_arr[col] = pd.to_numeric(df_old_arr[col], errors='coerce').fillna(0)
                today_dates = set(df_pivot_arr['Ngày vận hành'].unique())
                df_old_arr = df_old_arr[~df_old_arr['Ngày vận hành'].isin(today_dates)]
                df_final_arr = pd.concat([df_old_arr, df_pivot_arr[arrival_cols]], ignore_index=True)
            else:
                df_final_arr = df_pivot_arr[arrival_cols].copy()
                
            df_final_arr = df_final_arr.sort_values(
                by=['Ngày vận hành', 'Pickup_station', 'Scan Hour'],
                ascending=[False, True, True]
            )
            df_final_arr = df_final_arr[df_final_arr['Ngày vận hành'] >= '2026-07-05']
            
            # Lưu arrival.json
            os.makedirs("data", exist_ok=True)
            df_final_arr_json = df_final_arr.copy()
            df_final_arr_json.rename(columns={'Ngày vận hành': 'Ngy vn hnh', 'Tổng số đơn': 'Tng s n'}, inplace=True)
            df_final_arr_json.to_json(arrival_json_path, orient="records", force_ascii=False)
            print(f"   💾 Đã lưu file 'data/arrival.json' với {len(df_final_arr)} dòng.")
            
            # Ghi sheet Arrival (Đã bỏ qua theo yêu cầu để tối ưu hiệu năng)
            pass
                    
            # ----------------------------------------------------
            # 2. TẠO DATASET B: CHỈ HIỂN THỊ CÁC XE TRÊN ĐƯỜNG VỀ (CHƯA XẢ HÀNG XONG)
            # Xe được coi là đã về nếu trên xe có ít nhất 1 đơn đã được Inbound scan hôm nay
            inbound_today_wbs = set()
            for r in results.get('inbound', []):
                wb = str(r.get('billNo') or r.get('waybillNo') or '').strip().upper()
                if wb:
                    inbound_today_wbs.add(wb)

            from zoneinfo import ZoneInfo
            now_vn_eta = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
            today_op_date = get_operating_date(now_vn_eta.strftime('%Y-%m-%d %H:%M:%S'))

            # BN HUB / Northern +36h shift logic for incoming trucks operating date
            NORTH_POST_OFFICES_ETA = {
                'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
                'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
                'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
                'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
                'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
                'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
                'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
            }

            def get_truck_op_date(row):
                pkn = str(row.get('pickNetworkName') or row.get('inbound_network') or row.get('last_dept_name') or '').strip().upper()
                is_bn = (pkn == 'BN HUB' or pkn.startswith('HN ') or pkn.startswith('HD ') or pkn.startswith('HY ') or pkn in NORTH_POST_OFFICES_ETA)
                if is_bn:
                    scan_t = str(row.get('gio_di_thuc_te') or row.get('gio_bat_dau_xep') or row.get('scantime') or row.get('sendTime') or row.get('unloadingStartTime') or '').strip()
                    if scan_t and scan_t.lower() not in ('nan', 'none', ''):
                        try:
                            dt_scan = pd.to_datetime(scan_t, errors='coerce')
                            if pd.notna(dt_scan):
                                dt_shifted = dt_scan + pd.Timedelta(hours=36)
                                return get_operating_date(dt_shifted.strftime('%Y-%m-%d %H:%M:%S'))
                        except Exception:
                            pass
                return str(row.get('Ngày vận hành') or today_op_date).strip()

            if not df_enriched.empty:
                df_enriched['OpDate_Truck'] = df_enriched.apply(get_truck_op_date, axis=1)

            df_enriched_today = df_enriched[
                df_enriched.get('OpDate_Truck', df_enriched.get('Ngày vận hành', pd.Series([]))).astype(str).str.strip() == today_op_date
            ].copy() if not df_enriched.empty else pd.DataFrame()

            # Exclude vehicles/station trips where 50% or more of orders have ALREADY scanned Inbound at HUB
            if not df_enriched_today.empty:
                # Group by last_dept_name (Station) to calculate Inbound progress
                arrived_stations_50 = set()
                st_col = 'last_dept_name' if 'last_dept_name' in df_enriched_today.columns else 'Bưu cục'
                
                for st_name, grp in df_enriched_today.groupby(st_col):
                    st_clean = str(st_name).strip().upper()
                    if st_clean == 'BN HUB':
                        continue
                    tot_cnt = len(grp)
                    ib_cnt = sum(
                        1 for _, r in grp.iterrows() 
                        if str(r.get('billcode') or r.get('waybillNo') or '').strip().upper() in inbound_today_wbs 
                        or str(r.get('status_order') or r.get('status') or '').strip().lower() in ('đang trên bãi', 'inbound', 'nhập kho')
                    )
                    if tot_cnt > 0 and (ib_cnt / tot_cnt) >= 0.5:
                        arrived_stations_50.add(st_clean)

                def is_arrived_order(row):
                    st = str(row.get('last_dept_name') or row.get('Bưu cục') or '').strip().upper()
                    
                    # 1. Ràng buộc ngặt nghèo thời gian: Xe Shuttle có mốc đi thực tế đã quá 2.5 tiếng -> TỰ ĐỘNG GỠ (ĐÃ ĐẾN HUB)
                    if st != 'BN HUB':
                        scan_t = str(row.get('gio_di_thuc_te') or row.get('Pickup_time') or row.get('scantime') or row.get('dispatchNetworkTime') or '').strip()
                        if scan_t and scan_t.lower() not in ('nan', 'none', ''):
                            try:
                                dt_send = pd.to_datetime(scan_t, errors='coerce')
                                if pd.notna(dt_send) and dt_send < (now_vn_eta.replace(tzinfo=None) - timedelta(hours=2.5)):
                                    return True
                            except Exception:
                                pass

                    # 2. Ràng buộc 50% sản lượng trạm đã đến HUB
                    if st in arrived_stations_50:
                        return True
                        
                    bill = str(row.get('billcode') or row.get('waybillNo') or row.get('waybill_no') or '').strip().upper()
                    if bill and bill in inbound_today_wbs:
                        return True
                    status_str = str(row.get('status_order') or row.get('status') or row.get('trạng_thái') or '').strip().lower()
                    if any(kw in status_str for kw in ['nhập kho', 'inbound', 'trên bãi', 'đã đến', 'hoàn thành']):
                        return True
                    return False

                df_active = df_enriched_today[~df_enriched_today.apply(is_arrived_order, axis=1)].copy()
            else:
                df_active = pd.DataFrame()

            # Hàm đếm số lượng xe (số lượng transfercode duy nhất không rỗng)
            def count_unique_trucks(series):
                valid_trucks = series.dropna().astype(str).str.strip()
                valid_trucks = valid_trucks[(valid_trucks != '') & (valid_trucks.str.lower() != 'nan') & (valid_trucks.str.lower() != 'none')]
                val = int(valid_trucks.nunique())
                if val == 0 and not series.empty:
                    return 1
                return val
            
            # Nếu không có xe nào trên đường, tạo df_pivot_truck rỗng
            if not df_active.empty:
                # Group by transfercode (mã phiếu nhiệm vụ) so each vehicle is its own separate row with its own ETA
                if 'transfercode' not in df_active.columns:
                    df_active['transfercode'] = ''
                
                df_pivot_truck = (df_active.groupby(['Ngày vận hành', 'last_dept_name', 'Rank'])
                                  .agg(
                                      Trucking=('billcode', lambda x: 1),
                                      Orders=('billcode', 'count'),
                                      weight=('package_charge_weight', 'sum'),
                                      ETA=('ETA Incoming', 'first')
                                  ).reset_index())
                df_pivot_truck['transfercode'] = ''
                df_pivot_truck.rename(columns={'last_dept_name': 'Station'}, inplace=True)
                def format_eta(row):
                    eta_str = str(row.get('ETA') or '').strip()
                    if not eta_str or eta_str.lower() in ('nan', 'none'):
                        return ''
                    try:
                        dt = pd.to_datetime(eta_str, errors='coerce')
                        if pd.isna(dt):
                            return eta_str
                        if str(row.get('Rank')).strip().lower() == 'linehaul':
                            return dt.strftime('%d/%m %H:%M')
                        return dt.strftime('%H:%M')
                    except Exception:
                        return eta_str

                df_pivot_truck['ETA'] = df_pivot_truck.apply(format_eta, axis=1)
            else:
                df_pivot_truck = pd.DataFrame(columns=['Ngày vận hành', 'Station', 'Rank', 'transfercode', 'Trucking', 'Orders', 'weight', 'ETA'])
                
            truck_cols = ['Ngày vận hành', 'Station', 'Trucking', 'Orders', 'weight', 'ETA', 'Rank', 'transfercode']
            df_final_truck = df_pivot_truck[[c for c in truck_cols if c in df_pivot_truck.columns]].copy() if not df_pivot_truck.empty else pd.DataFrame(columns=truck_cols)
            
            # Filter out generic BN HUB aggregated rows if Linehaul details exist
            if not df_final_truck.empty:
                df_final_truck = df_final_truck[df_final_truck['Station'].astype(str).str.upper() != 'BN HUB']

            # Append active BN HUB Linehaul vehicles directly from data/linehaul.json (1 vehicle per transfercode)
            lh_json_path = "data/linehaul.json"
            if not os.path.exists(lh_json_path):
                lh_json_path = os.path.join(BASE_DIR, "data", "linehaul.json")
            if not os.path.exists(lh_json_path):
                lh_json_path = os.path.join(os.path.dirname(BASE_DIR), "data", "linehaul.json")
            if os.path.exists(lh_json_path):
                try:
                    with open(lh_json_path, 'r', encoding='utf-8') as f_lh:
                        lh_list = json.load(f_lh)
                    lh_rows_to_add = []
                    for lh_row in lh_list:
                        next_net = str(lh_row.get('nextNetworkName') or '').strip().upper()
                        unloading_end = str(lh_row.get('unloadingEndTime') or '').strip()
                        if next_net == 'BN HUB' and not unloading_end:
                            send_t = str(lh_row.get('sendTime') or '').strip()
                            orders_cnt = int(float(lh_row.get('billPiece') or 0))
                            w_kg = float(lh_row.get('weight') or 0)
                            pnv = str(lh_row.get('Phiếu nhiệm vụ') or '').strip()
                            
                            eta_formatted = ''
                            op_dt_truck = today_op_date
                            if send_t:
                                try:
                                    dt_send = pd.to_datetime(send_t)
                                    dt_shifted = dt_send + pd.Timedelta(hours=36)
                                    op_dt_truck = get_operating_date(dt_shifted.strftime('%Y-%m-%d %H:%M:%S'))
                                    eta_formatted = dt_shifted.strftime('%d/%m %H:%M')
                                except Exception:
                                    pass
                            
                            if orders_cnt > 0:
                                lh_rows_to_add.append({
                                    'Ngày vận hành': op_dt_truck,
                                    'Station': 'BN HUB',
                                    'Trucking': 1,
                                    'Orders': orders_cnt,
                                    'weight': w_kg,
                                    'ETA': eta_formatted,
                                    'Rank': 'Linehaul',
                                    'transfercode': pnv
                                })
                    if lh_rows_to_add:
                        df_lh_add = pd.DataFrame(lh_rows_to_add)
                        df_final_truck = pd.concat([df_final_truck, df_lh_add], ignore_index=True)
                except Exception as e_lh_err:
                    print(f"   ⚠️ Error loading linehaul.json for truck_eta: {e_lh_err}")

            # Sắp xếp theo ngày vận hành, trạm, ETA
            if not df_final_truck.empty:
                df_final_truck = df_final_truck.loc[:, ~df_final_truck.columns.duplicated()].copy()
                if 'Ngày vận hành' not in df_final_truck.columns and 'Ngy vn hnh' in df_final_truck.columns:
                    df_final_truck['Ngày vận hành'] = df_final_truck['Ngy vn hnh']
                if 'Ngy vn hnh' in df_final_truck.columns:
                    df_final_truck = df_final_truck.drop(columns=['Ngy vn hnh'])
                df_final_truck = df_final_truck.sort_values(
                    by=['Ngày vận hành', 'Station', 'ETA'],
                    ascending=[False, True, True]
                )
            
            # Ghi đè file truck_eta.json
            truck_json_path = "data/truck_eta.json"
            df_final_truck_json = df_final_truck.copy()
            df_final_truck_json.rename(columns={'Ngày vận hành': 'Ngy vn hnh'}, inplace=True)
            df_final_truck_json = df_final_truck_json.loc[:, ~df_final_truck_json.columns.duplicated()].copy()
            df_final_truck_json.to_json(truck_json_path, orient="records", force_ascii=False)
            print(f"   💾 Đã lưu file 'data/truck_eta.json' với {len(df_final_truck)} dòng (xe đang về).")
            
            # Ghi sheet Inbound Truck ETA - HCM HUB (Đã bỏ qua theo yêu cầu để tối ưu hiệu năng)
            pass
                    
        except Exception as e_piv:
            print(f'   ⚠️ Lỗi xử lý dữ liệu Arrival / Truck ETA: {e_piv}')
    else:
        print('   ⚠️ Không có dữ liệu Arrival để ghi sheet.')


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
        {"zone": "1", "area_id": "A06", "name": "BN HUB", "capacity": 1400},
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
        {"zone": "1", "area_id": "A19", "name": "AG LONG XUYÊN", "capacity": 780},
        {"zone": "1", "area_id": "A20", "name": "AG CẦN ĐĂNG", "capacity": 780}
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

        # --- Layout-critical overrides: take priority over valid.csv ---
        # BN HUB đã dời sang ô A06 (gộp), AG LONG XUYÊN → A19, AG CẦN ĐĂNG → A20
        FORCED_AREA_NAMES = {
            "A06": "BN HUB",
            "A19": "AG LONG XUYÊN",
            "A20": "AG CẦN ĐĂNG",
        }
        for key, info in master_chutes.items():
            c_id = info["area_id"]
            if c_id in FORCED_AREA_NAMES:
                info["name"] = FORCED_AREA_NAMES[c_id]

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

        # --- Force station→chute lookup for volume matching (MUST RUN LAST) ---
        # Đảm bảo volume từ JFS của BN HUB, AG LONG XUYÊN, AG CẦN ĐĂNG khớp đúng ô layout mới, ghi đè hoàn toàn valid.csv
        d_station_to_chute["BN HUB"] = "A06"
        d_station_to_chute["AG LONG XUYÊN"] = "A19"
        d_station_to_chute["AG CẦN ĐĂNG"] = "A20"
                    
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
            # ✅ Chỉ đọc đơn đang active (is_active=1) và chưa rời HUB
            df_db_inv = pd.read_sql_query(
                """SELECT dispatch_plan, next_station, pickNetworkName, status_order, weight, waybillNo, time_ref
                   FROM shipments
                   WHERE is_active = 1
                     AND status_order != 'Đã rời HUB'""",
                conn
            )
            conn.close()

            if not df_db_inv.empty:
                df_db_inv['dp_clean'] = df_db_inv['dispatch_plan'].astype(str).str.strip().str.upper()
                df_db_inv['next_st_clean'] = df_db_inv['next_station'].astype(str).str.strip().str.upper()
                df_db_inv['pick_st_clean'] = df_db_inv['pickNetworkName'].astype(str).str.strip().str.upper()
                
                NORTH_POST_OFFICES = {
                    'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
                    'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
                    'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
                    'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
                    'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
                    'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
                    'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
                }

                # Correct Outbound Chute Direction:
                # ❌ NEVER use pickNetworkName == 'BN HUB' for Outbound chute! (That is Inbound coming FROM BN HUB)
                # ✅ Outbound to BN HUB is ONLY when Destination (dispatch_plan/next_station) is BN HUB or Northern!
                def resolve_target_st(r):
                    dp = r['dp_clean']
                    ns = r['next_st_clean']
                    pk = r['pick_st_clean']

                    # 1. Check if destination is explicitly BN HUB or Northern linehaul
                    if dp == 'BN HUB' or ns == 'BN HUB':
                        return 'BN HUB'
                    if dp.startswith('HN ') or dp.startswith('HD ') or dp.startswith('HY ') or dp.startswith('BN ') or dp.startswith('TN ') or dp.startswith('THN ') or dp in NORTH_POST_OFFICES:
                        return 'BN HUB'

                    # 2. Map standard Outbound destination
                    if dp and dp not in ('HCM HUB', 'NONE', 'NAN'):
                        return dp
                    if ns and ns not in ('HCM HUB', 'NONE', 'NAN'):
                        return ns
                    
                    # 3. Fallback origin only for satellite post offices (exclude BN HUB origin!)
                    if pk != 'BN HUB' and not pk.startswith('HN ') and not pk.startswith('HD ') and not pk.startswith('HY ') and pk not in NORTH_POST_OFFICES:
                        return pk

                    return 'EXCLUDE_INBOUND'

                df_db_inv['target_st'] = df_db_inv.apply(resolve_target_st, axis=1)
                df_db_inv = df_db_inv[df_db_inv['target_st'] != 'EXCLUDE_INBOUND'].copy()
                df_db_inv['layout_name'] = df_db_inv['target_st'].apply(map_station_to_layout_name)
                df_db_inv['status_upper'] = df_db_inv['status_order'].astype(str).str.strip()
                
                # Loại bỏ các đơn có nguồn gốc (pickNetworkName) từ miền Bắc/BN HUB ở trạng thái "Đang trên đường"
                NORTH_POST_OFFICES = {
                    'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
                    'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
                    'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
                    'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
                    'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
                    'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
                    'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
                }
                pkn_series = df_db_inv['pickNetworkName'].astype(str).str.strip().str.upper()
                is_north_origin = (
                    pkn_series.str.startswith('HN ') |
                    pkn_series.str.startswith('HD ') |
                    pkn_series.str.startswith('HY ') |
                    (pkn_series == 'BN HUB') |
                    pkn_series.isin(NORTH_POST_OFFICES)
                )
                df_db_inv = df_db_inv[~((is_north_origin) & (df_db_inv['status_upper'] == 'Đang trên đường'))]
                
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
    t_overall_start = time.time()

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

    days_back = rebuild_days if rebuild_days is not None else 3

    if not last_run_dt:
        last_run_dt = now - timedelta(days=1)

    DATE_START_STANDARD = (now - timedelta(days=days_back)).strftime('%Y-%m-%d') + ' 06:00:00'
    DATE_START_FORECAST = (now - timedelta(days=1)).strftime('%Y-%m-%d') + ' 06:00:00'
    
    min_dispatch_dt = now - timedelta(days=days_back)
    if is_rebuild:
        effective_dispatch_start_dt = min_dispatch_dt
    else:
        effective_dispatch_start_dt = max(last_run_dt - timedelta(minutes=30), min_dispatch_dt)
    DATE_START_DISPATCH = effective_dispatch_start_dt.strftime('%Y-%m-%d %H:%M:%S')
    
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
    print(f"📅 Range (Standard): {DATE_START_STANDARD} → {DATE_END}\n📅 Range (Forecast): {DATE_START_FORECAST} → {DATE_END}\n📅 Range (Dispatch): {DATE_START_DISPATCH} → {DATE_END}")
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
    for k in ['timeStart', 'inputTimeStart']: fp[k] = DATE_START_FORECAST
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
    task_times = {}
    t_start_parallel = time.time()
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
                task_times[key] = time.time() - t_start_parallel
            except Exception as e:
                print(f"   ⚠️ {key} lỗi: {e}")
                results[key] = []
                task_times[key] = time.time() - t_start_parallel

    print("\n🔗 Xử lý & join data...")

    # Load active records from SQLite
    db_records = {}
    init_db()
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # ── [FIX-TZ] Tính ngưỡng thời gian bằng Python localtime (UTC+7) thay vì
        #    dùng datetime('now', '+7 hours') trong SQLite vì có thể bị lệch múi giờ ──
        _now_local    = datetime.now()
        _thresh_3days = (_now_local - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
        _thresh_2days = (_now_local - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')

        # Tự động dọn dẹp các đơn kẹt quá 3 ngày không có log xuất kho
        # 1. Đối với các đơn đã quét Inbound
        c.execute("""
            UPDATE shipments 
            SET status_order = 'Đã rời HUB', is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate != '' AND inbound_scanDate IS NOT NULL)
              AND inbound_scanDate < ?
        """, (_thresh_3days,))
        cnt1 = c.rowcount
        
        # 2. Đối với các đơn mới chỉ ở trạng thái Forecast/Pickup (chưa có inbound scan)
        c.execute("""
            UPDATE shipments 
            SET is_active = 0, last_updated = CURRENT_TIMESTAMP
            WHERE is_active = 1
              AND (inbound_scanDate = '' OR inbound_scanDate IS NULL)
              AND (
                (Pickup_time != '' AND Pickup_time IS NOT NULL AND Pickup_time < ?)
                OR
                ((Pickup_time = '' OR Pickup_time IS NULL) AND time_ref < ?)
              )
        """, (_thresh_3days, _thresh_3days))
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
              AND dispatchNetworkTime < ?
        """, (_thresh_2days,))
        cnt3 = c.rowcount
        conn.commit()
        if cnt3 > 0:
            print(f"   🧹 Dọn dẹp Dispatch cũ: Đã tắt {cnt3:,} đơn Dispatch không có inbound/pickup quá 2 ngày.")

        if cnt1 + cnt2 + cnt3 > 0:
            print(f"   🧹 Tự động dọn dẹp: Đã chuyển {cnt1:,} đơn kẹt Inbound → 'Đã rời HUB', tắt {cnt2:,} đơn Forecast/Pickup cũ (>3 ngày), tắt {cnt3:,} đơn Dispatch cũ (>2 ngày).")

        # [FIX-BACKLOG] Reset is_backlog = 0 CHỈ cho đơn còn active.
        # Không reset đơn đã is_active=0 để bảo toàn lịch sử backlog.
        c.execute("UPDATE shipments SET is_backlog = 0 WHERE is_active = 1")
        conn.commit()
            
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

    def update_if_changed(rec, key, new_val):
        old_val = rec.get(key)
        if key == 'weight':
            try:
                old_f = float(old_val) if old_val is not None and old_val != '' else 0.0
                new_f = float(new_val) if new_val is not None and new_val != '' else 0.0
                if abs(old_f - new_f) > 0.0001:
                    rec[key] = new_f
                    rec['changed'] = True
                    return True
                return False
            except (ValueError, TypeError):
                pass
        
        old_str = str(old_val or '').strip()
        new_str = str(new_val or '').strip()
        if old_str != new_str:
            rec[key] = new_str
            rec['changed'] = True
            return True
        return False

    def get_or_create_record(wb, conn=None):
        if wb in db_records:
            return db_records[wb], False
            
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(DB_FILE)
            close_conn = True
            
        c_check = conn.cursor()
        c_check.execute("SELECT * FROM shipments WHERE waybillNo = ?", (wb,))
        row = c_check.fetchone()
        if row:
            col_names = [description[0] for description in c_check.description]
            rec = dict(zip(col_names, row))
            if close_conn:
                conn.close()
            db_records[wb] = rec
            return rec, False
            
        if close_conn:
            conn.close()
        rec = {
            'waybillNo': wb, 'data_source': '', 'weight': 0.0, 'pickNetworkName': '', 'dispatch_plan': '',
            'Pickup_time': '', 'pickup_label': '', 'Pickup_ontime': '', 'dispatchNetworkTime': '',
            'next_station': '', 'Tuyến': '', 'Rank': '', 'inbound_network': '', 'inbound_scanDate': '',
            'outbound_scanDate': '', 'Arrival_time': '', 'dispatch_actual': '', 'status_order': '', 'time_ref': '',
            'is_backlog': 0, 'is_active': 1, 'retry_count': 0, 'last_retry_time': ''
        }
        db_records[wb] = rec
        return rec, True

    # Open shared SQLite connection for efficient batch query/caching
    conn_db = sqlite3.connect(DB_FILE)

    # 1. Process Forecast
    df_fc = pd.DataFrame(results.get('forecast', []))
    if not df_fc.empty:
        for _, r in df_fc.iterrows():
            wb = str(r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            rec, is_new = get_or_create_record(wb, conn_db)
            if is_new:
                rec['changed'] = True
            update_if_changed(rec, 'data_source', 'Forecast')
            pick_net = d_buucuc.get(str(r.get('pickNetworkName', '')).strip(), str(r.get('pickNetworkName', '')).strip())
            update_if_changed(rec, 'pickNetworkName', pick_net)
            disp_plan = str(r.get('dispatchNetworkName') or '').strip()
            if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                disp_plan = str(r.get('terminalDispatchCode') or r.get('transferDispatchCode') or r.get('receiverSortingCode') or '').strip()
            update_if_changed(rec, 'dispatch_plan', disp_plan)
            
            try:
                w_val = r.get('loadWeight') or r.get('weight') or rec.get('weight') or 0.0
                update_if_changed(rec, 'weight', float(w_val))
            except (ValueError, TypeError):
                pass
            
            delivery_time = str(r.get('deliveryTime') or '').strip()
            if delivery_time and delivery_time.lower() not in ('nan', 'none', ''):
                update_if_changed(rec, 'Pickup_time', delivery_time)

            if not rec.get('inbound_scanDate') and not rec.get('outbound_scanDate'):
                update_if_changed(rec, 'is_active', 1)

            if is_new or rec.get('status_order') in ('', 'Đã rời HUB'):
                update_if_changed(rec, 'status_order', 'Đã điều phối bưu cục')

            fc_time_str = str(
                r.get('dispatchNetworkTime') or
                r.get('shippingTime') or
                r.get('orderTime') or
                r.get('createTime') or
                r.get('inputTime') or
                r.get('deliveryTime') or
                ''
            ).strip()
            if fc_time_str and fc_time_str.lower() not in ('nan', 'none', ''):
                update_if_changed(rec, 'dispatchNetworkTime', fc_time_str)
            elif not rec.get('dispatchNetworkTime'):
                update_if_changed(rec, 'dispatchNetworkTime', now_vn.strftime('%Y-%m-%d %H:%M:%S'))

    # 2. Process Dispatch
    df_dp = pd.DataFrame(results.get('dispatch', []))
    if not df_dp.empty:
        for _, r in df_dp.iterrows():
            wb = str(r.get('waybillId') or r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            rec, is_new = get_or_create_record(wb, conn_db)
            if is_new:
                rec['changed'] = True
            update_if_changed(rec, 'data_source', 'Dispatch')
            pick_net = d_buucuc.get(str(r.get('pickNetworkName', '')).strip(), str(r.get('pickNetworkName', '')).strip())
            update_if_changed(rec, 'pickNetworkName', pick_net)
            disp_plan = str(r.get('dispatchNetworkName') or '').strip()
            if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                disp_plan = str(r.get('terminalDispatchCode') or r.get('transferDispatchCode') or r.get('receiverSortingCode') or '').strip()
            update_if_changed(rec, 'dispatch_plan', disp_plan)
            
            try:
                w_val = r.get('packageChargeWeight') or r.get('weight') or rec.get('weight') or 0.0
                update_if_changed(rec, 'weight', float(w_val))
            except (ValueError, TypeError):
                pass
            
            disp_time = str(
                r.get('dispatchNetworkTime') or
                r.get('createTime') or
                r.get('inputTime') or
                r.get('orderDispatchTime') or
                r.get('orderTime') or
                ''
            ).strip()
            if disp_time and disp_time.lower() not in ('nan', 'none', ''):
                update_if_changed(rec, 'dispatchNetworkTime', disp_time)
                
            status_dp = str(r.get('orderStatusName') or '').strip()
            update_time = str(r.get('updateTime') or '').strip()
            if status_dp == 'Đã lấy hàng' and update_time and update_time.lower() not in ('nan', 'none', ''):
                update_if_changed(rec, 'Pickup_time', update_time)

    # 3. Process Arrival Scans (Max scan time per waybill)
    arrival_raw = results.get('arrival', [])
    arrival_max = {}
    for r in arrival_raw:
        wb = str(r.get('billcode') or r.get('waybillNo') or r.get('billNo') or '').strip()
        scan_time = str(
            r.get('unloadingStartTime') or
            r.get('unloadingEndTime') or
            r.get('arrival_time') or
            r.get('gio_di_thuc_te') or
            r.get('gio_bat_dau_xep') or
            r.get('scantime') or
            r.get('ETA Incoming') or
            ''
        ).strip()
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in arrival_max or scan_time > arrival_max[wb]:
                arrival_max[wb] = scan_time
                
    for wb, scan_time in arrival_max.items():
        rec, is_new = get_or_create_record(wb, conn_db)
        if is_new:
            rec['changed'] = True
        if not rec.get('data_source'):
            update_if_changed(rec, 'data_source', 'Arrival')
        if not rec.get('dispatchNetworkTime'):
            update_if_changed(rec, 'dispatchNetworkTime', scan_time)
        if not rec.get('Arrival_time') or scan_time > rec['Arrival_time']:
            update_if_changed(rec, 'Arrival_time', scan_time)

    # 4. Process Inbound Scans (Max scan time per waybill)
    inbound_raw = results.get('inbound', [])
    inbound_max = {}
    for r in inbound_raw:
        wb = str(r.get('billNo') or r.get('waybillNo') or '').strip()
        scan_time = str(r.get('scanDate') or '').strip()
        send_site = str(r.get('sendSite') or '').strip()
        try:
            wt = float(r.get('weight') or r.get('settlementWeight') or r.get('bulkWeight') or 0.0)
        except (ValueError, TypeError):
            wt = 0.0
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in inbound_max or scan_time > inbound_max[wb]['time']:
                inbound_max[wb] = {'time': scan_time, 'site': send_site, 'weight': wt}
                
    for wb, info in inbound_max.items():
        rec, is_new = get_or_create_record(wb, conn_db)
        if is_new:
            rec['changed'] = True
        if not rec.get('data_source'):
            update_if_changed(rec, 'data_source', 'Inbound')
        if not rec.get('inbound_scanDate') or info['time'] > rec['inbound_scanDate']:
            update_if_changed(rec, 'inbound_scanDate', info['time'])
            update_if_changed(rec, 'inbound_network', d_buucuc.get(info['site'], info['site']))
        if info.get('weight') and (rec.get('weight') is None or rec.get('weight') == 0.0):
            update_if_changed(rec, 'weight', info['weight'])

    # 5. Process Outbound Scans (Max scan time per waybill)
    outbound_raw = results.get('outbound', [])
    outbound_max = {}
    for r in outbound_raw:
        wb = str(r.get('billNo') or r.get('waybillNo') or '').strip()
        scan_time = str(r.get('scanDate') or '').strip()
        next_station = str(r.get('upOrNextStation') or '').strip()
        try:
            wt = float(r.get('weight') or r.get('settlementWeight') or r.get('bulkWeight') or 0.0)
        except (ValueError, TypeError):
            wt = 0.0
        if wb and scan_time and scan_time.lower() not in ('nan', 'none', ''):
            if wb not in outbound_max or scan_time > outbound_max[wb]['time']:
                outbound_max[wb] = {'time': scan_time, 'station': next_station, 'weight': wt}
                
    for wb, info in outbound_max.items():
        rec, is_new = get_or_create_record(wb, conn_db)
        if is_new:
            rec['changed'] = True
        if not rec.get('outbound_scanDate') or info['time'] > rec['outbound_scanDate']:
            update_if_changed(rec, 'outbound_scanDate', info['time'])
            update_if_changed(rec, 'dispatch_actual', d_buucuc.get(info['station'], info['station']))
        if info.get('weight') and (rec.get('weight') is None or rec.get('weight') == 0.0):
            update_if_changed(rec, 'weight', info['weight'])

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
        rec, is_new = get_or_create_record(wb, conn_db)
        if is_new:
            rec['changed'] = True
        update_if_changed(rec, 'is_backlog', 1)
        update_if_changed(rec, 'outbound_scanDate', '')
        
        dest = str(r.get('destination_site_name') or '').strip()
        abn = str(r.get('abnormal_remark') or '').strip()
        if abn in BACKLOG_REDELIVER_REMARKS:
            take_site = str(r.get('take_site_name') or '').strip()
            if take_site:
                dest = take_site
        dest_mapped = d_buucuc.get(dest, dest)
        update_if_changed(rec, 'dispatch_plan', dest)
        update_if_changed(rec, 'next_station', dest_mapped)

    # Close shared SQLite connection
    conn_db.close()

    # 7. Unified Completion Sync (Vòng 2 - rolling window & retry limit)
    t_start_completion = time.time()
    
    # Configuration loading
    BATCH_SIZE = 500
    ROLLING_SYNC_DAYS = 7
    MAX_RETRY_COUNT = 10
    
    config_path = os.path.join(BASE_DIR, "config", "sync_config.json")
    if os.path.exists(config_path):
        try:
            cfg = load_json(config_path)
            BATCH_SIZE = int(cfg.get("BATCH_SIZE", 500))
            ROLLING_SYNC_DAYS = int(cfg.get("ROLLING_SYNC_DAYS", 3))
            MAX_RETRY_COUNT = int(cfg.get("MAX_RETRY_COUNT", 10))
        except Exception:
            pass
            
    # Calculate rolling window date boundary
    rolling_boundary_str = (now - timedelta(days=ROLLING_SYNC_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    
    pending_wbs_list = []
    
    for wb, rec in db_records.items():
        is_missing_dispatch = not rec.get('dispatchNetworkTime') or str(rec.get('dispatchNetworkTime')).strip().lower() in ('nan', 'none', '')
        if (
            rec.get('is_active', 1) == 1
            and (rec.get('status_order') != 'Đã rời HUB' or is_missing_dispatch)
        ):
            # Verify if time_ref falls within the rolling window
            ref_val = str(rec.get('time_ref') or rec.get('last_updated') or '').strip()
            if not ref_val or ref_val < rolling_boundary_str:
                continue
                
            pkn = rec.get('pickNetworkName') or ''
            dp_plan = rec.get('dispatch_plan') or ''
            pk_time = rec.get('Pickup_time') or ''
            disp_time = rec.get('dispatchNetworkTime') or ''
            retry_cnt = int(rec.get('retry_count') or 0)
            
            is_case_a = False
            is_case_b = False
            is_case_c = False
            
            if rec.get('data_source') in ('Forecast', 'Dispatch'):
                is_case_a = (not pkn or not dp_plan) and (retry_cnt < MAX_RETRY_COUNT)
                is_case_b = (pkn and dp_plan) and not pk_time
                is_case_c = not disp_time and (retry_cnt < MAX_RETRY_COUNT)
            else:
                is_case_c = not disp_time and (retry_cnt < MAX_RETRY_COUNT)
                
            if is_case_a or is_case_b or is_case_c:
                pending_wbs_list.append((ref_val, wb, is_case_a or is_case_c))
                
    # Prioritize newer shipments: sort DESC by time_ref
    pending_wbs_list.sort(key=lambda x: x[0] or '', reverse=True)
    
    # Cap total waybills at 10000
    pending_wbs_list = pending_wbs_list[:10000]
    total_pending = len(pending_wbs_list)
    
    completion_recovered = 0
    total_batches = (total_pending + BATCH_SIZE - 1) // BATCH_SIZE if total_pending > 0 else 0
    
    if total_pending > 0:
        dh_path = os.path.join(BASE_DIR, "config", "dispatchheaders.json")
        dp_path = os.path.join(BASE_DIR, "config", "dispatchpayload.json")
        if os.path.exists(dh_path) and os.path.exists(dp_path):
            try:
                dh = load_json(dh_path)
                dp_cfg = load_json(dp_path)
                
                # Reuse the existing session & token_mgr to avoid invalidating each other's tokens
                dh['authToken'] = token_mgr.get_token()
                dh['Authtoken'] = token_mgr.get_token()
                dh['Routename'] = 'orderScheduling'
                dh['routeName'] = 'orderScheduling'
                
                print(f"\n🔍 [Completion Sync] Khởi chạy: {total_pending:,} đơn | {total_batches} batch | BATCH_SIZE: {BATCH_SIZE}")
                
                for b_idx in range(total_batches):
                    t_batch_start = time.time()
                    batch_items = pending_wbs_list[b_idx * BATCH_SIZE : (b_idx + 1) * BATCH_SIZE]
                    chunk = [item[1] for item in batch_items]
                    
                    payload = dp_cfg.copy()
                    payload['waybillIds'] = ",".join(chunk)
                    payload['current'] = 1
                    payload['size'] = len(chunk)
                    
                    # Set 30-day window for indexing/partitioning (crucial for J&T performance)
                    now_tz = now
                    start_time = (now_tz - timedelta(days=30)).strftime('%Y-%m-%d') + ' 00:00:00'
                    end_time = now_tz.strftime('%Y-%m-%d') + ' 23:59:59'
                    
                    payload['startInputTime'] = start_time
                    payload['endInputTime'] = end_time
                    payload['timeType'] = "1"
                    if 'startPickTime' in payload:
                        payload['startPickTime'] = ""
                    if 'endPickTime' in payload:
                        payload['endPickTime'] = ""
                            
                    batch_updated = 0
                    
                    # Wrap query in a try-except block with batch-level retries
                    dp_res = None
                    max_batch_attempts = 3
                    for attempt in range(max_batch_attempts):
                        try:
                            r_dp = auth_post(session, URL_DISPATCH, token_mgr, dh, data=payload, timeout=25, max_retries=2, label=f'Completion Sync Batch {b_idx + 1}/{total_batches} (Attempt {attempt + 1})')
                            dp_res = r_dp.json()
                            break
                        except Exception as e_api:
                            if attempt == max_batch_attempts - 1:
                                print(f"      ❌ Lỗi kết nối API đợt {b_idx + 1} sau {max_batch_attempts} lần thử: {e_api}")
                            else:
                                print(f"      ⚠️ Lỗi kết nối API đợt {b_idx + 1}: {e_api}. Đang thử lại sau {(attempt + 1) * 2}s...")
                                time.sleep((attempt + 1) * 2)
                    
                    if dp_res is None:
                        continue
                        
                    try:
                        data_node = dp_res.get('data', {})
                        records = []
                        if isinstance(data_node, dict):
                            records = data_node.get('records', []) or []
                        elif isinstance(data_node, list):
                            records = data_node
                            
                        resolved_items = {}
                        for item in records:
                            if not isinstance(item, dict):
                                continue
                            waybill_id = str(item.get('waybillId') or item.get('waybillNo') or '').strip()
                            if waybill_id:
                                disp_time = str(item.get('dispatchNetworkTime') or item.get('inputTime') or item.get('createTime') or '').strip()
                                pickup_time = str(item.get('pickTime') or item.get('updateTime') or '').strip()
                                order_status = str(item.get('orderStatusName') or '').strip()
                                
                                pk_val = pickup_time if (order_status == 'Đã lấy hàng' and pickup_time) else ''
                                
                                disp_plan = str(item.get('dispatchNetworkName') or '').strip()
                                if not disp_plan or disp_plan.lower() in ('nan', 'none'):
                                    disp_plan = str(item.get('terminalDispatchCode') or item.get('transferDispatchCode') or item.get('receiverSortingCode') or '').strip()
                                    
                                pick_net = (
                                    str(item.get('pickNetworkName') or '').strip()
                                    or str(item.get('collectNetworkName') or '').strip()
                                    or str(item.get('sendSiteName') or '').strip()
                                )
                                
                                try:
                                    w_val = float(item.get('packageChargeWeight') or item.get('weight') or 0.0)
                                except (ValueError, TypeError):
                                    w_val = 0.0
                                
                                resolved_items[waybill_id] = {
                                    'dispatchNetworkTime': disp_time,
                                    'Pickup_time': pk_val,
                                    'status_order': order_status,
                                    'dispatch_plan': disp_plan,
                                    'pickNetworkName': pick_net,
                                    'weight': w_val
                                }
                                
                        # Apply updates to db_records and increment retry_count for Case A
                        for item_info in batch_items:
                            _, wb, is_case_a = item_info
                            rec = db_records[wb]
                            
                            # Increment retry count for Case A only on successful API request
                            if is_case_a:
                                rec['retry_count'] = int(rec.get('retry_count') or 0) + 1
                            rec['last_retry_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
                            rec['changed'] = True
                            
                            if wb in resolved_items:
                                info = resolved_items[wb]
                                
                                # Update fields if available
                                if info['dispatchNetworkTime'] and info['dispatchNetworkTime'].lower() not in ('nan', 'none', ''):
                                    rec['dispatchNetworkTime'] = info['dispatchNetworkTime']
                                if info['Pickup_time']:
                                    rec['Pickup_time'] = info['Pickup_time']
                                if info['dispatch_plan'] and info['dispatch_plan'].lower() not in ('nan', 'none', ''):
                                    rec['dispatch_plan'] = info['dispatch_plan']
                                if info['pickNetworkName'] and info['pickNetworkName'].lower() not in ('nan', 'none', ''):
                                    rec['pickNetworkName'] = d_buucuc.get(info['pickNetworkName'], info['pickNetworkName'])
                                if info.get('weight') and (rec.get('weight') is None or rec.get('weight') == 0.0):
                                    rec['weight'] = info['weight']
                                    
                                if info['status_order'] and info['status_order'].lower() not in ('nan', 'none', ''):
                                    curr_status = rec.get('status_order', '')
                                    if curr_status in ('', 'Forecast', 'Đã điều phối bưu cục'):
                                        rec['status_order'] = info['status_order']
                                        
                                # If all three fields are now populated, we count it as fully recovered
                                if rec.get('pickNetworkName') and rec.get('dispatch_plan') and rec.get('Pickup_time'):
                                    batch_updated += 1
                                    
                        completion_recovered += batch_updated
                        
                    except Exception as e_batch:
                        print(f"      ⚠️ Lỗi xử lý dữ liệu batch {b_idx + 1}/{total_batches}: {e_batch}")
                        
                    # Thêm độ trễ nhỏ để tránh rate-limit JFS API
                    time.sleep(0.5)
                        
                    t_batch_elapsed = time.time() - t_batch_start
                    batch_pending_count = len(chunk) - batch_updated
                    print(f"   Completion Sync | Batch {b_idx + 1} / {total_batches} | Processing: {len(chunk)} shipments | Updated: {batch_updated} | Still Pending: {batch_pending_count} | Elapsed: {t_batch_elapsed:.2f}s")
                    
            except Exception as e_setup:
                print(f"   ❌ Lỗi cấu hình Completion Sync: {e_setup}")
                
    t_completion_elapsed = time.time() - t_start_completion
    still_pending_total = total_pending - completion_recovered
    completion_success_rate = (completion_recovered / total_pending * 100) if total_pending > 0 else 0.0
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

            # Triệt tiêu trùng mốc ảo: Nếu Pickup_time trùng hệt dispatchNetworkTime -> gán rỗng Pickup_time
            if rec.get('Pickup_time') and rec.get('dispatchNetworkTime') and rec['Pickup_time'] == rec['dispatchNetworkTime']:
                rec['Pickup_time'] = ""

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
            rec['Next_station'] = (rec.get('Next_station') or rec.get('next_station') or '').strip()

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
        t_ref = ob_time if ob_time else (ib_time if ib_time else (pk_time if pk_time else (fc_time if fc_time else arr_time)))
        
        # Apply +36 hours shift for northern (BN HUB) shipments that are not yet inbound/outbound
        pkn = str(rec.get('pickNetworkName') or '').strip().upper()
        NORTH_POST_OFFICES = {
            'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
            'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
            'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
            'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
            'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
            'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
            'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
        }
        is_north = (
            pkn.startswith('HN ') or 
            pkn.startswith('HD ') or 
            pkn.startswith('HY ') or 
            pkn == 'BN HUB' or
            pkn in NORTH_POST_OFFICES
        )
        if is_north and not ob_time and not ib_time and arr_time:
            try:
                arr_dt = pd.to_datetime(arr_time)
                shifted_arr_dt = arr_dt + pd.Timedelta(hours=36)
                t_ref = shifted_arr_dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
                
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
                int(rec.get('is_backlog', 0)), int(rec.get('is_active', 1)),
                int(rec.get('retry_count', 0)), str(rec.get('last_retry_time') or '')
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
                    is_backlog, is_active, retry_count, last_retry_time, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(waybillNo) DO UPDATE SET
                    -- Nhóm B: Luôn luôn cập nhật trạng thái hoạt động và metadata
                    data_source         = excluded.data_source,
                    status_order        = excluded.status_order,
                    is_backlog          = excluded.is_backlog,
                    is_active           = excluded.is_active,
                    retry_count         = excluded.retry_count,
                    last_retry_time     = excluded.last_retry_time,
                    last_updated        = CURRENT_TIMESTAMP,

                    -- Nhóm A: Bảo vệ dữ liệu. Chỉ ghi đè nếu DB cũ chưa có (rỗng/NULL/0.0)
                    weight = CASE 
                        WHEN (shipments.weight IS NULL OR shipments.weight = 0.0) AND excluded.weight IS NOT NULL AND excluded.weight > 0 
                        THEN excluded.weight ELSE shipments.weight END,
                        
                    dispatch_plan = CASE 
                        WHEN (shipments.dispatch_plan IS NULL OR shipments.dispatch_plan = '') 
                        THEN excluded.dispatch_plan ELSE shipments.dispatch_plan END,
                        
                    dispatchNetworkTime = CASE 
                        WHEN (shipments.dispatchNetworkTime IS NULL OR shipments.dispatchNetworkTime = '') 
                        THEN excluded.dispatchNetworkTime ELSE shipments.dispatchNetworkTime END,
                        
                    pickNetworkName = CASE 
                        WHEN (shipments.pickNetworkName IS NULL OR shipments.pickNetworkName = '') 
                        THEN excluded.pickNetworkName ELSE shipments.pickNetworkName END,
                        
                    Pickup_time = CASE 
                        WHEN (shipments.Pickup_time IS NULL OR shipments.Pickup_time = '') 
                        THEN excluded.Pickup_time ELSE shipments.Pickup_time END,
                        
                    pickup_label = CASE 
                        WHEN (shipments.pickup_label IS NULL OR shipments.pickup_label = '') 
                        THEN excluded.pickup_label ELSE shipments.pickup_label END,
                        
                    Pickup_ontime = CASE 
                        WHEN (shipments.Pickup_ontime IS NULL OR shipments.Pickup_ontime = '') 
                        THEN excluded.Pickup_ontime ELSE shipments.Pickup_ontime END,
                        
                    next_station = CASE 
                        WHEN (shipments.next_station IS NULL OR shipments.next_station = '') 
                        THEN excluded.next_station ELSE shipments.next_station END,
                        
                    Tuyến = CASE 
                        WHEN (shipments.Tuyến IS NULL OR shipments.Tuyến = '') 
                        THEN excluded.Tuyến ELSE shipments.Tuyến END,
                        
                    Rank = CASE 
                        WHEN (shipments.Rank IS NULL OR shipments.Rank = '') 
                        THEN excluded.Rank ELSE shipments.Rank END,
                        
                    inbound_network = CASE 
                        WHEN (shipments.inbound_network IS NULL OR shipments.inbound_network = '') 
                        THEN excluded.inbound_network ELSE shipments.inbound_network END,
                        
                    inbound_scanDate = CASE 
                        WHEN (shipments.inbound_scanDate IS NULL OR shipments.inbound_scanDate = '') 
                        THEN excluded.inbound_scanDate ELSE shipments.inbound_scanDate END,
                        
                    outbound_scanDate = CASE 
                        WHEN (shipments.outbound_scanDate IS NULL OR shipments.outbound_scanDate = '') 
                        THEN excluded.outbound_scanDate ELSE shipments.outbound_scanDate END,
                        
                    Arrival_time = CASE 
                        WHEN (shipments.Arrival_time IS NULL OR shipments.Arrival_time = '') 
                        THEN excluded.Arrival_time ELSE shipments.Arrival_time END,
                        
                    dispatch_actual = CASE 
                        WHEN (shipments.dispatch_actual IS NULL OR shipments.dispatch_actual = '') 
                        THEN excluded.dispatch_actual ELSE shipments.dispatch_actual END,
                        
                    time_ref = CASE 
                        WHEN (shipments.time_ref IS NULL OR shipments.time_ref = '') 
                        THEN excluded.time_ref ELSE shipments.time_ref END
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
        return get_op_date_clean(fc_time)
        
    df['Ngày vận hành_Forecast'] = df.apply(calc_fc_op_date, axis=1)
    
    def calc_pk_op_date(row):
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
    
    export_heatmap_json()

    # Write last successful run timestamp
    try:
        with open(last_run_file, "w") as f:
            f.write(now.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Write last_update.json for frontend
        os.makedirs("data", exist_ok=True)
        with open("data/last_update.json", "w", encoding="utf-8") as f_json:
            json.dump({"last_update": now.strftime('%H:%M:%S %d/%m/%Y')}, f_json, ensure_ascii=False)
            
        print(f"   ✅ Đã ghi nhận thời gian chạy cuối: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e_lr:
        print(f"   ⚠️ Lỗi ghi file last_run.txt / last_update.json: {e_lr}")

    t_overall_elapsed = time.time() - t_overall_start
    t_fc = task_times.get('forecast', 0.0)
    t_dp = task_times.get('dispatch', 0.0)
    t_ib = task_times.get('inbound', 0.0)
    t_ob = task_times.get('outbound', 0.0)
    t_bl = task_times.get('backlog', 0.0)
    
    print("\n========== ETL SUMMARY ==========")
    print("Daily Sync")
    print(f"  Forecast ............ {t_fc:.1f}s")
    print(f"  Dispatch ............ {t_dp:.1f}s")
    print(f"  Inbound ............. {t_ib:.1f}s")
    print(f"  Outbound ............ {t_ob:.1f}s")
    print(f"  Backlog ............. {t_bl:.1f}s")
    print("Completion Sync")
    print(f"  Pending Shipments ... {total_pending:,}")
    print(f"  Batches ............. {total_batches}")
    print(f"  Recovered ........... {completion_recovered:,}")
    print(f"  Still Pending ....... {still_pending_total:,}")
    print(f"  Success Rate ........ {completion_success_rate:.1f}%")
    print(f"  Total Runtime ....... {t_overall_elapsed:.1f}s")
    print("==================================\n")


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
                            UPDATE shipments
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
                c_rt.execute("SELECT waybillNo FROM shipments WHERE status_order = 'Đang trên bãi'")
                db_wbs = {row[0] for row in c_rt.fetchall()}
                stale = db_wbs - live_wbs
                if stale:
                    c_rt.executemany(
                        "UPDATE shipments SET status_order = 'Đã rời HUB', last_updated = CURRENT_TIMESTAMP WHERE waybillNo = ?",
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
    # ── Singleton lock để tránh chạy chồng chéo gây xung đột token (405) ──
    lock_file = os.path.join(BASE_DIR, "sync.lock")
    try:
        if os.name == 'nt':
            import msvcrt
            lock_fp = open(lock_file, 'w')
            try:
                msvcrt.locking(lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
            except IOError:
                print("❌ Lỗi: Script đang chạy ở một tiến trình khác (Windows lock). Thoát để tránh xung đột token (405).")
                sys.exit(0)
        else:
            import fcntl
            lock_fp = open(lock_file, 'w')
            try:
                fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                print("❌ Lỗi: Script đang chạy ở một tiến trình khác (Unix lock). Thoát để tránh xung đột token (405).")
                sys.exit(0)
    except Exception:
        pass

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
    # [FIX-MIRROR] Lock và retry để tránh WinError 32 (file being used by another process)
    FILE_WRITE_LOCK = threading.Lock()
    
    def safe_mirror_copy(src, dest, max_retries=5):
        import shutil
        import time
        dest_tmp = dest + ".tmp"
        for attempt in range(1, max_retries + 1):
            try:
                with FILE_WRITE_LOCK:
                    shutil.copy2(src, dest_tmp)
                    os.replace(dest_tmp, dest)
                return True
            except PermissionError:
                if os.path.exists(dest_tmp):
                    try: os.remove(dest_tmp)
                    except Exception: pass
                if attempt == max_retries:
                    # Final fallback: try direct copyfile
                    try:
                        shutil.copyfile(src, dest)
                        return True
                    except Exception as pe_final:
                        print(f"   ⚠️ Warning mirror {os.path.basename(src)}: {pe_final}")
                        return False
                time.sleep(0.5 * attempt)
            except Exception as e_copy:
                if os.path.exists(dest_tmp):
                    try: os.remove(dest_tmp)
                    except Exception: pass
                print(f"   ⚠️ Lỗi copy {os.path.basename(src)}: {e_copy}")
                return False
        return False

    try:
        dest_dirs = [os.path.join("..", "data"), os.path.join("..", "src", "data")]
        repo_base = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"
        if os.path.exists(repo_base):
            dest_dirs.append(os.path.join(repo_base, "data"))
            dest_dirs.append(os.path.join(repo_base, "src", "data"))
            
        for dest_dir in dest_dirs:
            os.makedirs(dest_dir, exist_ok=True)
            if os.path.exists("data"):
                for fn in os.listdir("data"):
                    if fn.endswith(".json") or fn.endswith(".gz"):
                        safe_mirror_copy(os.path.join("data", fn), os.path.join(dest_dir, fn))
        print("   📂 Đã đồng bộ tất cả file JSON ra các thư mục data/ và src/data/ (Desktop & Git repo).")
    except Exception as e_mir:
        print(f"   ⚠️ Lỗi mirror data: {e_mir}")

    # Auto git commit & push for local synchronization runs
    try:
        import subprocess
        git_dir = repo_base if (os.path.exists(repo_base) and os.path.exists(os.path.join(repo_base, ".git"))) else (".." if os.path.exists(os.path.join("..", ".git")) else ".")
        root_data_dir = os.path.join(git_dir, "data")
        files_to_add = []
        if os.path.exists(root_data_dir):
            for fn in os.listdir(root_data_dir):
                if fn.endswith(".json") or fn.endswith(".gz"):
                    files_to_add.append(os.path.join("data", fn))
        
        src_data_dir = os.path.join(git_dir, "src", "data")
        if os.path.exists(src_data_dir):
            for fn in os.listdir(src_data_dir):
                if fn.endswith(".json") or fn.endswith(".gz"):
                    files_to_add.append(os.path.join("src", "data", fn))
                    
        if files_to_add:
            print(f"   🔄 Tự động stage, commit và push dữ liệu mới lên GitHub ({git_dir})...")

            # Stage files directly without stash
            subprocess.run(["git", "add"] + files_to_add, cwd=git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            res_commit = subprocess.run(["git", "commit", "-m", f"Auto-sync local data update ({datetime.now().strftime('%H:%M %d/%m')})"], cwd=git_dir, capture_output=True, text=True)
            
            # Pull rebase remote changes first if any
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=git_dir, capture_output=True, text=True)

            res_push = subprocess.run(["git", "push", "origin", "main"], cwd=git_dir, capture_output=True, text=True)
            if res_push.returncode == 0:
                print("   ✅ Đã đẩy dữ liệu mới lên GitHub thành công!")
            else:
                print(f"   ⚠️ Reminded push status: {res_push.stderr.strip()[:150]}")
    except Exception as e_git:
        print(f"   ⚠️ Lỗi tự động Git push: {e_git}")



if __name__ == "__main__":
    main()