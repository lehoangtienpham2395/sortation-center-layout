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
# TUNING — đã tối ưu để tăng tốc ~5x so với mặc định
# ============================================================
SOURCE_WORKERS      = 8   # ⚡ Tăng từ 5 → 8: song song giữa các nguồn API
PAGE_WORKERS        = 10  # ⚡ Tăng từ 2 → 10: song song khi kéo pages
POOL_SIZE           = 64  # ⚡ Tăng connection pool để hỗ trợ nhiều worker
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
    
    # Auto dọn dẹp các record ĐÃ RỜI HUB cũ hơn 7 ngày để tối ưu hóa dung lượng DB.
    # Các đơn CHƯA RỜI HUB (đang bám đuổi) sẽ được giữ lại vô thời hạn.
    try:
        limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("""
            DELETE FROM inventory 
            WHERE status_order = 'Đã rời HUB' 
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
    df['scantime_dt'] = pd.to_datetime(df.get('scantime'), errors='coerce')
    df['Ngày vận hành'] = (df['scantime_dt'] - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d')
    df['Scan Hour']     = df['scantime_dt'].dt.hour.fillna(-1).astype(int)

    # Logic đặc biệt cho BN HUB:
    # 1. Ngày vận hành = Ngày xuất phát gốc + 36 tiếng (chu kỳ Bắc-Nam thực tế).
    #    Lấy trực tiếp ngày dương lịch cập bến làm Ngày vận hành (không trừ 6h cycle vận hành của bưu cục).
    # 2. Scan Hour giữ nguyên giờ quét gốc của bưu cục phát.
    if 'scansitename' in df.columns:
        df = df.rename(columns={'scansitename': 'Pickup_station'})
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
        return r.json().get('data', []) or []

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
    try:
        sheet = ss.worksheet("Outbound")
    except Exception:
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


def update_backlog_sheet(ss, master_chutes, backlog_volumes, current_date_str):
    try:
        sheet = ss.worksheet("Backlog")
    except Exception:
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


def update_inventory_sheet(ss, master_chutes, inventory_volumes, current_date_str):
    try:
        sheet = ss.worksheet("Inventory")
    except Exception:
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


def update_inbound_sheets(ss, results, master_chutes, d_buucuc, session=None, token_mgr=None, fh=None, fp=None):
    print("\n📥 Bắt đầu cập nhật dữ liệu Inbound gom nhóm theo trạng thái & khung giờ lên Google Sheets...")
    
    def write_sheet(sheet_name, df_data, headers):
        try:
            sheet = ss.worksheet(sheet_name)
        except Exception:
            try:
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

    # Tải mốc thời gian lấy hàng lịch sử từ SQLite để mapping chính xác cho các đơn đã về HUB
    db_waybill_times = {}
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT waybillNo, Pickup_time, dispatchNetworkTime FROM inventory")
        rows = c.fetchall()
        for r in rows:
            wb = r[0]
            pk = r[1] if r[1] else ''
            disp = r[2] if r[2] else ''
            db_waybill_times[wb] = (pk, disp)
        conn.close()
        print(f"   ℹ| Load được {len(db_waybill_times):,} mốc thời gian từ SQLite để mapping.")
    except Exception as e_db:
        print(f"   ⚠️ Lỗi load mốc thời gian từ SQLite: {e_db}")

    awb_records = {}

    df_dp_raw = pd.DataFrame(results.get('dispatch', []))
    df_fc_raw = pd.DataFrame(results.get('forecast', []))
    df_in_raw = pd.DataFrame(results.get('inbound', []))

    # --- Step 1 & 2: Unified AWB Mapping & Deduplication ---
    
    # 1. Process Dispatch first (primary dataset)
    if not df_dp_raw.empty:
        for _, r in df_dp_raw.iterrows():
            wb = str(r.get('waybillNo') or r.get('waybillId', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            weight = float(r.get('packageChargeWeight') or r.get('weight') or 0.0)
            
            # Map raw dispatch values
            dispatch_time = str(r.get('dispatchNetworkTime') or '').strip()
            status_dp = str(r.get('orderStatusName') or '').strip()
            update_time = str(r.get('updateTime') or '').strip()
            
            # Pickup Time is updateTime if status is 'Đã lấy hàng'
            pickup_time = ''
            if status_dp == 'Đã lấy hàng' and update_time and update_time.lower() not in ('nan', 'none'):
                pickup_time = update_time
                
            awb_records[wb] = {
                'waybill': wb,
                'fc': fc_mapped,
                'weight': weight,
                'forecast_time': dispatch_time if (dispatch_time and dispatch_time.lower() not in ('nan', 'none')) else '',
                'pickup_time': pickup_time,
                'inbound_time': '',
                'source': 'Dispatch'
            }

    # 2. Process Forecast (map/merge into Dispatch, or create new record if missing)
    if not df_fc_raw.empty:
        for _, r in df_fc_raw.iterrows():
            wb = str(r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            
            delivery_time = str(r.get('deliveryTime') or '').strip()
            if delivery_time.lower() in ('nan', 'none'):
                delivery_time = ''
                
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            weight = float(r.get('loadWeight') or 0.0)
            
            if wb in awb_records:
                # Merge: if pickup_time is empty, use delivery_time as fallback
                if not awb_records[wb]['pickup_time'] and delivery_time:
                    awb_records[wb]['pickup_time'] = delivery_time
            else:
                # Create new record
                awb_records[wb] = {
                    'waybill': wb,
                    'fc': fc_mapped,
                    'weight': weight,
                    'forecast_time': '',
                    'pickup_time': delivery_time,
                    'inbound_time': '',
                    'source': 'Forecast'
                }

    # 3. Process Inbound (map scanDate into each record)
    if not df_in_raw.empty:
        # A. On-Demand JFS query to fetch missing pickup/dispatch times for inbound bills
        missing_wbs = []
        for _, r in df_in_raw.iterrows():
            wb = str(r.get('billNo') or r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
            
            # Check if this waybill has missing pickup_time in our in-memory map or SQLite
            pk_db, _ = db_waybill_times.get(wb, ('', ''))
            pk_mem = awb_records.get(wb, {}).get('pickup_time', '')
            
            if not pk_db and not pk_mem:
                missing_wbs.append(wb)
                
        missing_wbs = list(set(missing_wbs))
        if missing_wbs and session and token_mgr and fh and fp:
            print(f"   ℹ️ Phát hiện {len(missing_wbs)} đơn Inbound thiếu mốc giờ lấy hàng. Tiến hành truy vấn trực tiếp JFS...")
            chunk_size = 80
            resolved_count = 0
            
            headers = fh.copy()
            headers['authToken'] = token_mgr.get_token()
            headers['Authtoken'] = token_mgr.get_token()
            
            conn_db = None
            c_db = None
            try:
                conn_db = sqlite3.connect(DB_FILE)
                c_db = conn_db.cursor()
            except Exception as e_db:
                print(f"   ⚠️ Lỗi kết nối DB để lưu cache: {e_db}")
                
            for i in range(0, len(missing_wbs), chunk_size):
                chunk = missing_wbs[i:i+chunk_size]
                payload = fp.copy()
                payload['waybillNos'] = ",".join(chunk)
                for k in ['timeStart', 'inputTimeStart', 'timeEnd', 'inputTimeEnd']:
                    if k in payload:
                        payload[k] = ""
                        
                try:
                    new_token = token_mgr.get_token()
                    headers['authToken'] = new_token
                    headers['Authtoken'] = new_token
                    
                    r_fc = session.post(URL_FORECAST, headers=headers, data=payload, timeout=15)
                    raw_json = r_fc.json()
                    
                    if not isinstance(raw_json, dict):
                        continue
                        
                    fc_res = raw_json.get('data', []) or []
                    if isinstance(fc_res, dict):
                        fc_res = fc_res.get('records', []) or []
                        
                    for item in fc_res:
                        if not isinstance(item, dict):
                            continue
                        wb = str(item.get('waybillNo', '')).strip()
                        pk = str(item.get('collectTime') or item.get('deliveryTime') or '').strip()
                        disp = str(item.get('dispatchNetworkTime') or '').strip()
                        
                        if wb and pk and pk.lower() not in ('nan', 'none'):
                            db_waybill_times[wb] = (pk, disp)
                            resolved_count += 1
                            
                            # Cache in SQLite
                            if c_db:
                                try:
                                    c_db.execute("""
                                        UPDATE inventory 
                                        SET Pickup_time = ?, dispatchNetworkTime = ?, time_ref = ?
                                        WHERE waybillNo = ?
                                    """, (pk, disp, pk, wb))
                                except Exception:
                                    pass
                except Exception as e_q:
                    print(f"   ⚠️ Lỗi truy vấn JFS cho chunk {i//chunk_size}: {e_q}")
                    
            if conn_db:
                try:
                    conn_db.commit()
                    conn_db.close()
                except Exception:
                    pass
            print(f"   ✅ Đã phân tích & bổ sung thành công {resolved_count} mốc thời gian từ JFS.")

        # B. Map Inbound scanDate to awb_records
        for _, r in df_in_raw.iterrows():
            wb = str(r.get('billNo') or r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
                
            ib_time = str(r.get('scanDate', '')).strip()
            if ib_time.lower() in ('nan', 'none'):
                ib_time = ''
                
            weight = float(r.get('weight') or 0.0)
            fc = str(r.get('sendSite', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            
            if wb in awb_records:
                awb_records[wb]['inbound_time'] = ib_time
                if weight > 0:
                    awb_records[wb]['weight'] = weight
            else:
                # Orphan Inbound: Create new record
                awb_records[wb] = {
                    'waybill': wb,
                    'fc': fc_mapped,
                    'weight': weight,
                    'forecast_time': '',
                    'pickup_time': '',
                    'inbound_time': ib_time,
                    'source': 'Inbound'
                }

    # 4. Integrate SQLite Cached Times (Fallback for Inbound/Dispatch/Forecast)
    for wb, rec in awb_records.items():
        pk_db, disp_db = db_waybill_times.get(wb, ('', ''))
        
        # If SQLite has Pickup Time and memory record is missing it
        if pk_db and not rec['pickup_time']:
            rec['pickup_time'] = pk_db
        # If SQLite has Dispatch Time and memory record is missing it
        if disp_db and not rec['forecast_time']:
            rec['forecast_time'] = disp_db

    # --- Step 4 & 5: Centralized Timestamp Priority & Column Generation ---
    from zoneinfo import ZoneInfo
    now_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    current_op_date = get_operating_date(now_vn)
    
    unique_rows = []
    
    for wb, rec in awb_records.items():
        ib_time = rec['inbound_time']
        pk_time = rec['pickup_time']
        fc_time = rec['forecast_time']
        
        # 1. Shipment Status Priority Engine
        if ib_time:
            status = "Đã về Hub"
        elif pk_time:
            status = "Lấy hàng thành công"
        elif fc_time:
            status = "Điều phối bưu cục"
        else:
            status = "Forecast"
            
        # 2. Status-specific Operation Dates
        op_date_ib = get_operating_date(ib_time) if ib_time else ""
        
        fc_time_temp = fc_time
        if (not fc_time_temp or fc_time_temp.lower() in ('nan', 'none')) and status == 'Forecast':
            fc_time_temp = pk_time
        op_date_fc = get_operating_date(fc_time_temp) if fc_time_temp else ""
        
        op_date_pk = ""
        if status not in ('Forecast', 'Đã điều phối bưu cục') and pk_time:
            op_date_pk = get_operating_date(pk_time)
            
        # 3. Drop Type (Loại rớt)
        if status == "Đã về Hub":
            loai_rot = "Rớt hôm nay"
        else:
            if op_date_fc:
                if op_date_pk:
                    if op_date_fc == op_date_pk:
                        loai_rot = "Rớt hôm nay"
                    else:
                        loai_rot = "Rớt hôm trước"
                else:
                    if op_date_fc < current_op_date:
                        loai_rot = "Rớt hôm trước"
                    else:
                        loai_rot = "Rớt hôm nay"
            else:
                loai_rot = "Rớt hôm nay"
                
        # 4. Format Hours
        ib_hour = ""
        if ib_time:
            try:
                ib_hour = pd.to_datetime(ib_time).strftime('%Y-%m-%d %H:00')
            except Exception:
                pass
                
        fc_hour = ""
        if fc_time:
            try:
                fc_hour = pd.to_datetime(fc_time).strftime('%Y-%m-%d %H:00')
            except Exception:
                pass
                
        pk_hour = ""
        if pk_time:
            try:
                pk_hour = pd.to_datetime(pk_time).strftime('%Y-%m-%d %H:00')
            except Exception:
                pass
                
        unique_rows.append({
            'Bưu cục': rec['fc'],
            'Trạng thái': status,
            'weight': rec['weight'],
            'Ngày vận hành_Inbound': op_date_ib,
            'Ngày vận hành_Forecast': op_date_fc,
            'Ngày vận hành_Pickup': op_date_pk,
            'Inbound Hour': ib_hour,
            'Forecast Time': fc_hour,
            'Pickup Time': pk_hour,
            'Loại rớt': loai_rot,
            'waybill': wb
        })

    # --- Step 6: Backlog Carryover Projection ---
    projected_rows = []
    for r in unique_rows:
        projected_rows.append(r)
        # Carry over un-inbounded records from past operating dates to today's date
        if r['Trạng thái'] != 'Đã về Hub' and r['Trạng thái'] != 'Đã nhập hàng':
            if r['Ngày vận hành_Forecast'] and r['Ngày vận hành_Forecast'] < current_op_date:
                dup = r.copy()
                dup['Ngày vận hành_Forecast'] = current_op_date
                dup['Loại rớt'] = 'Rớt hôm trước'
                projected_rows.append(dup)
            elif r['Ngày vận hành_Pickup'] and r['Ngày vận hành_Pickup'] < current_op_date:
                dup = r.copy()
                dup['Ngày vận hành_Pickup'] = current_op_date
                dup['Loại rớt'] = 'Rớt hôm trước'
                projected_rows.append(dup)

    # --- Step 7: Grouping & Aggregation ---
    grouped = {}
    for r in projected_rows:
        key = (
            r['Bưu cục'], r['Trạng thái'],
            r['Ngày vận hành_Inbound'], r['Ngày vận hành_Forecast'], r['Ngày vận hành_Pickup'],
            r['Inbound Hour'], r['Forecast Time'], r['Pickup Time'], r['Loại rớt']
        )
        if key not in grouped:
            grouped[key] = {'volume': 0, 'weight': 0.0}
        grouped[key]['volume'] += 1
        grouped[key]['weight'] += r['weight']
        
    final_rows = []
    for (fc_name, status, op_ib, op_fc, op_pk, ib_hour, fc_hour, pk_hour, loai_rot), stats in grouped.items():
        final_rows.append({
            'Bưu cục': fc_name,
            'Trạng thái': status,
            'Volume': stats['volume'],
            'Weight': int(stats['weight']),
            'Ngày vận hành_Inbound': op_ib,
            'Ngày vận hành_Forecast': op_fc,
            'Ngày vận hành_Pickup': op_pk,
            'Inbound Hour': ib_hour,
            'Forecast Time': fc_hour,
            'Pickup Time': pk_hour,
            'Loại rớt': loai_rot
        })
        
    df_inbound_aggregated = pd.DataFrame(final_rows)
    write_sheet("Inbound", df_inbound_aggregated, [
        "Bưu cục", "Trạng thái", "Volume", "Weight",
        "Ngày vận hành_Inbound", "Ngày vận hành_Forecast", "Ngày vận hành_Pickup",
        "Inbound Hour", "Forecast Time", "Pickup Time", "Loại rớt"
    ])

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
            # Ưu tiên lấy waybillNo hoặc waybillId (chứa mã vận đơn thực tế của Inbound thô) trước billNo (thường bị rỗng)
            bn_col = 'waybillNo' if 'waybillNo' in df_in_raw.columns else ('waybillId' if 'waybillId' in df_in_raw.columns else ('billNo' if 'billNo' in df_in_raw.columns else None))
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
                arr_sheet = ss.worksheet('Arrival')
            except Exception:
                try:
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


def update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, current_date_str, results=None, d_buucuc=None, session=None, token_mgr=None, fh=None, fp=None):
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
        
        # Open spreadsheet once
        ss = gc.open_by_key(SHEET_ID)
        
        # Load master chutes from sheet1 (first sheet)
        master_chutes = {}
        try:
            first_sheet = ss.sheet1
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
            update_outbound_sheet(ss, master_chutes, outbound_volumes_grouped, target_dates)
            
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
                        backlog_volumes = df_live_bl.groupby('next_station_upper').agg(
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
            update_inventory_sheet(ss, master_chutes, inventory_volumes, current_date_str)
            
        # 4. Update Inbound Sheets (aggregated Inbound + raw Linehaul + Arrival)
        if results:
            update_inbound_sheets(ss, results, master_chutes, d_buucuc, session, token_mgr, fh, fp)
            
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
        last_run_dt = now - timedelta(days=4)

    DATE_START_STANDARD = (now - timedelta(days=4)).strftime('%Y-%m-%d') + ' 06:00:00'
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

    # Khởi tạo token manager riêng biệt cho nguồn Arrival sử dụng tài khoản 660085
    print("🔐 Khởi tạo TokenManager riêng biệt cho Arrival (User: 660085)...")
    arrival_token_mgr = TokenManager(session, "660085", "246@Hoang", COUNTRY_ID)
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
            ex.submit(pull_arrival_from_jfs, session, arrival_token_mgr, ih, DATE_START_STANDARD, DATE_END): 'arrival',
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

    # ✅ Đồng bộ hóa actual pickup time (updateTime) vào Pickup_time (của các đơn Đã lấy hàng)
    # để lưu đúng thời gian lấy hàng thực tế vào SQLite & Google Sheet
    if 'updateTime' in df_all.columns:
        df_all['updateTime'] = df_all['updateTime'].fillna('').astype(str).str.strip()
        df_all['Pickup_time'] = df_all['Pickup_time'].fillna('').astype(str).str.strip()
        
        is_picked_up = (df_all['status_order'] == 'Đã lấy hàng') & (df_all['updateTime'] != '') & (df_all['updateTime'] != 'nan')
        df_all.loc[is_picked_up, 'Pickup_time'] = df_all.loc[is_picked_up, 'updateTime']

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

    # --- Step 3: Load historical SQLite state.db inventory table ---
    db_records = {}
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM inventory")
        rows = c.fetchall()
        if rows:
            col_names = [description[0] for description in c.description]
            for r in rows:
                rec = dict(zip(col_names, r))
                db_records[rec['waybillNo']] = rec
        conn.close()
        print(f"   ℹ| Load được {len(db_records):,} đơn lịch sử từ SQLite để thực hiện Incremental Merge.")
    except Exception as e_db:
        print(f"   ⚠️ Lỗi load đơn từ SQLite: {e_db}")

    # --- Step 4: Normalize AWB and Merge with 4-day API data ---
    new_records = {}
    
    # 1. Dispatch (primary dataset)
    if not df_dp_lookup.empty:
        for _, r in df_dp_lookup.iterrows():
            wb = str(r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none'):
                continue
            
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            weight = float(r.get('weight') or r.get('packageChargeWeight') or 0.0)
            dispatch_plan = str(r.get('dispatch_plan') or '').strip()
            
            dispatch_time = str(r.get('dispatchNetworkTime') or '').strip()
            status_dp = str(r.get('status_order') or '').strip()
            update_time = str(r.get('updateTime') or '').strip()
            
            # Pickup time is updateTime if status is 'Đã lấy hàng'
            pickup_time = ''
            if status_dp == 'Đã lấy hàng' and update_time and update_time.lower() not in ('nan', 'none'):
                pickup_time = update_time
                
            next_station = str(r.get('next_station') or '').strip()
            
            new_records[wb] = {
                'waybillNo': wb,
                'data_source': 'Dispatch',
                'weight': weight,
                'pickNetworkName': fc_mapped,
                'dispatch_plan': dispatch_plan,
                'dispatchNetworkTime': dispatch_time if (dispatch_time and dispatch_time.lower() not in ('nan', 'none')) else '',
                'updateTime': update_time if (update_time and update_time.lower() not in ('nan', 'none')) else '',
                'Pickup_time': pickup_time,
                'next_station': next_station,
                'status_order': status_dp,
                'inbound_scanDate': '',
                'inbound_network': '',
                'outbound_scanDate': '',
                'dispatch_actual': ''
            }

    # 2. Forecast (merge or add new)
    if not df_fc.empty:
        for _, r in df_fc.iterrows():
            wb = str(r.get('waybillNo') or '').strip()
            if not wb or wb.lower() in ('nan', 'none'):
                continue
            
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            weight = float(r.get('weight') or r.get('loadWeight') or 0.0)
            dispatch_plan = str(r.get('dispatch_plan') or '').strip()
            delivery_time = str(r.get('Pickup_time') or r.get('deliveryTime') or '').strip()
            next_station = str(r.get('next_station') or '').strip()
            
            if wb in new_records:
                # Merge into existing Dispatch record
                if not new_records[wb]['Pickup_time'] and delivery_time and delivery_time.lower() not in ('nan', 'none'):
                    new_records[wb]['Pickup_time'] = delivery_time
            else:
                # Create a new Forecast record
                new_records[wb] = {
                    'waybillNo': wb,
                    'data_source': 'Forecast',
                    'weight': weight,
                    'pickNetworkName': fc_mapped,
                    'dispatch_plan': dispatch_plan,
                    'dispatchNetworkTime': '',
                    'updateTime': '',
                    'Pickup_time': delivery_time if (delivery_time and delivery_time.lower() not in ('nan', 'none')) else '',
                    'next_station': next_station,
                    'status_order': '',
                    'inbound_scanDate': '',
                    'inbound_network': '',
                    'outbound_scanDate': '',
                    'dispatch_actual': ''
                }

    # 3. Inbound (merge or add new)
    if not df_in.empty:
        for _, r in df_in.iterrows():
            wb = str(r.get('billNo') or r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none'):
                continue
                
            ib_time = str(r.get('inbound_scanDate') or r.get('scanDate') or '').strip()
            ib_net = str(r.get('inbound_network') or r.get('sendSite') or '').strip()
            ib_net_mapped = d_buucuc.get(ib_net, ib_net)
            
            if wb in new_records:
                new_records[wb]['inbound_scanDate'] = ib_time if (ib_time and ib_time.lower() not in ('nan', 'none')) else ''
                new_records[wb]['inbound_network'] = ib_net_mapped
            else:
                # Orphan Inbound
                new_records[wb] = {
                    'waybillNo': wb,
                    'data_source': 'Inbound',
                    'weight': 0.0,
                    'pickNetworkName': ib_net_mapped,
                    'dispatch_plan': '',
                    'dispatchNetworkTime': '',
                    'updateTime': '',
                    'Pickup_time': '',
                    'next_station': '',
                    'status_order': '',
                    'inbound_scanDate': ib_time if (ib_time and ib_time.lower() not in ('nan', 'none')) else '',
                    'inbound_network': ib_net_mapped,
                    'outbound_scanDate': '',
                    'dispatch_actual': ''
                }

    # 4. Outbound (merge or add new)
    if not df_out.empty:
        for _, r in df_out.iterrows():
            wb = str(r.get('billNo') or r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none'):
                continue
                
            ob_time = str(r.get('outbound_scanDate') or r.get('scanDate') or '').strip()
            ob_act = str(r.get('dispatch_actual') or r.get('upOrNextStation') or '').strip()
            ob_act_mapped = d_buucuc.get(ob_act, ob_act)
            
            if wb in new_records:
                new_records[wb]['outbound_scanDate'] = ob_time if (ob_time and ob_time.lower() not in ('nan', 'none')) else ''
                new_records[wb]['dispatch_actual'] = ob_act_mapped
            else:
                # Orphan Outbound
                new_records[wb] = {
                    'waybillNo': wb,
                    'data_source': 'Outbound',
                    'weight': 0.0,
                    'pickNetworkName': '',
                    'dispatch_plan': '',
                    'dispatchNetworkTime': '',
                    'updateTime': '',
                    'Pickup_time': '',
                    'next_station': ob_act_mapped,
                    'status_order': '',
                    'inbound_scanDate': '',
                    'inbound_network': '',
                    'outbound_scanDate': ob_time if (ob_time and ob_time.lower() not in ('nan', 'none')) else '',
                    'dispatch_actual': ob_act_mapped
                }


    # ================================================================
    # BATCH SEARCH DISPATCH API FOR FORECAST/INBOUND AWBS MISSING DISPATCH NETWORK TIME
    # ================================================================
    missing_disp_wbs = []
    for wb, rec in new_records.items():
        if rec['data_source'] in ('Forecast', 'Inbound', 'Outbound') and not rec.get('dispatchNetworkTime'):
            missing_disp_wbs.append(wb)
            
    for wb, rec in db_records.items():
        if rec.get('data_source') in ('Forecast', 'Inbound', 'Outbound') and not rec.get('dispatchNetworkTime'):
            t_ref = rec.get('time_ref') or rec.get('Pickup_time') or rec.get('inbound_scanDate') or ''
            if t_ref:
                try:
                    dt = pd.to_datetime(t_ref)
                    if (now - dt.tz_localize('Asia/Ho_Chi_Minh' if dt.tzinfo is None else None)).days <= 15:
                        missing_disp_wbs.append(wb)
                except Exception:
                    pass
                    
    missing_disp_wbs = list(set(missing_disp_wbs))
    
    if missing_disp_wbs:
        print(f"\n🔍 [Batch Search] Phát hiện {len(missing_disp_wbs):,} đơn Forecast/Inbound chưa có dispatchNetworkTime.")
        print("   🚀 Tiến hành Batch search trực tiếp trên Dispatch API sử dụng parameter 'waybillIds'...")
        
        dh_path = os.path.join(BASE_DIR, "config", "dispatchheaders.json")
        dp_path = os.path.join(BASE_DIR, "config", "dispatchpayload.json")
        
        if os.path.exists(dh_path) and os.path.exists(dp_path):
            try:
                dh = load_json(dh_path)
                dp_cfg = load_json(dp_path)
                
                dh['authToken'] = token_mgr.get_token()
                dh['Authtoken'] = token_mgr.get_token()
                dh['Routename'] = 'orderScheduling'
                dh['routeName'] = 'orderScheduling'
                
                chunk_size = 50
                resolved_disp = {}
                
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
                        r_dp = session.post(URL_DISPATCH, headers=dh, data=payload, timeout=25)
                        dp_res = r_dp.json()
                        records = dp_res.get('data', {}).get('records', []) or []
                        if records:
                            for item in records:
                                waybill_id = str(item.get('waybillId') or '').strip()
                                if waybill_id:
                                    disp_time = str(item.get('dispatchNetworkTime') or item.get('inputTime') or item.get('createTime') or '').strip()
                                    pickup_time = str(item.get('updateTime') or '').strip()
                                    order_status = str(item.get('orderStatusName') or '').strip()
                                    
                                    pk_val = pickup_time if (order_status == 'Đã lấy hàng' and pickup_time) else ''
                                    
                                    if disp_time and disp_time.lower() not in ('nan', 'none', ''):
                                        resolved_disp[waybill_id] = {
                                            'dispatchNetworkTime': disp_time,
                                            'Pickup_time': pk_val,
                                            'status_order': order_status
                                        }
                    except Exception as e_batch:
                        print(f"      ⚠️ Lỗi query batch chunk {i//chunk_size}: {e_batch}")
                        
                print(f"   ✅ [Batch Search] Hoàn tất: Tìm thấy thông tin Dispatch cho {len(resolved_disp):,} / {len(missing_disp_wbs):,} đơn.")
                
                for wb, info in resolved_disp.items():
                    if wb in new_records:
                        new_records[wb]['dispatchNetworkTime'] = info['dispatchNetworkTime']
                        if info['Pickup_time']:
                            new_records[wb]['Pickup_time'] = info['Pickup_time']
                        new_records[wb]['data_source'] = 'Dispatch'
                        
                    if wb in db_records:
                        db_records[wb]['dispatchNetworkTime'] = info['dispatchNetworkTime']
                        if info['Pickup_time']:
                            db_records[wb]['Pickup_time'] = info['Pickup_time']
                        db_records[wb]['data_source'] = 'Dispatch'
                        db_records[wb]['changed'] = True
                        
            except Exception as e_setup:
                print(f"   ❌ Lỗi cấu hình Batch search: {e_setup}")
    # ================================================================

    # Perform Merge & preservation / dynamic update checks
    changed_count = 0
    
    for wb, new_rec in new_records.items():
        if wb in db_records:
            hist_rec = db_records[wb]
            changed = False
            
            # Rule 3: Finalize Inbound Time (do not overwrite historical Inbound Time if present)
            hist_ib = str(hist_rec.get('inbound_scanDate') or '').strip()
            new_ib = str(new_rec.get('inbound_scanDate') or '').strip()
            final_ib = hist_ib
            if (not hist_ib or hist_ib.lower() in ('nan', 'none')) and new_ib and new_ib.lower() not in ('nan', 'none'):
                final_ib = new_ib
                changed = True
                
            # Rule 4: Dynamic Timestamps Update (Pickup & Forecast times)
            hist_pk = str(hist_rec.get('Pickup_time') or '').strip()
            new_pk = str(new_rec.get('Pickup_time') or '').strip()
            final_pk = hist_pk
            if new_pk and new_pk.lower() not in ('nan', 'none') and new_pk != hist_pk:
                final_pk = new_pk
                changed = True
                
            hist_disp = str(hist_rec.get('dispatchNetworkTime') or '').strip()
            new_disp = str(new_rec.get('dispatchNetworkTime') or '').strip()
            final_disp = hist_disp
            if new_disp and new_disp.lower() not in ('nan', 'none') and new_disp != hist_disp:
                final_disp = new_disp
                changed = True
                
            # Other fields update
            final_weight = float(hist_rec.get('weight') or 0.0)
            if new_rec['weight'] > 0 and new_rec['weight'] != final_weight:
                final_weight = new_rec['weight']
                changed = True
                
            final_pkn = str(hist_rec.get('pickNetworkName') or '').strip()
            if new_rec['pickNetworkName'] and new_rec['pickNetworkName'] != final_pkn:
                final_pkn = new_rec['pickNetworkName']
                changed = True
                
            final_dpl = str(hist_rec.get('dispatch_plan') or '').strip()
            if new_rec['dispatch_plan'] and new_rec['dispatch_plan'] != final_dpl:
                final_dpl = new_rec['dispatch_plan']
                changed = True
                
            final_nst = str(hist_rec.get('next_station') or '').strip()
            if new_rec['next_station'] and new_rec['next_station'] != final_nst:
                final_nst = new_rec['next_station']
                changed = True
                
            hist_ob = str(hist_rec.get('outbound_scanDate') or '').strip()
            new_ob = str(new_rec.get('outbound_scanDate') or '').strip()
            final_ob = hist_ob
            if new_ob and new_ob.lower() not in ('nan', 'none') and new_ob != hist_ob:
                final_ob = new_ob
                changed = True
                
            hist_act = str(hist_rec.get('dispatch_actual') or '').strip()
            new_act = str(new_rec.get('dispatch_actual') or '').strip()
            final_act = hist_act
            if new_act and new_act.lower() not in ('nan', 'none') and new_act != hist_act:
                final_act = new_act
                changed = True
                
            final_ds = str(hist_rec.get('data_source') or '').strip()
            if new_rec['data_source'] != 'Forecast' and new_rec['data_source'] != final_ds:
                final_ds = new_rec['data_source']
                changed = True
                
            # Update DB dict
            db_records[wb]['weight'] = final_weight
            db_records[wb]['pickNetworkName'] = final_pkn
            db_records[wb]['dispatch_plan'] = final_dpl
            db_records[wb]['Pickup_time'] = final_pk
            db_records[wb]['dispatchNetworkTime'] = final_disp
            db_records[wb]['next_station'] = final_nst
            db_records[wb]['inbound_scanDate'] = final_ib
            db_records[wb]['outbound_scanDate'] = final_ob
            db_records[wb]['dispatch_actual'] = final_act
            db_records[wb]['data_source'] = final_ds
            
            if changed:
                db_records[wb]['changed'] = True
                changed_count += 1
        else:
            # AWB is new: insert
            new_rec['changed'] = True
            new_rec['pickup_label'] = ''
            new_rec['Pickup_ontime'] = ''
            new_rec['Tuyến'] = ''
            new_rec['Rank'] = ''
            new_rec['time_ref'] = ''
            new_rec['inbound_network'] = new_rec['pickNetworkName']
            db_records[wb] = new_rec
            changed_count += 1
            
    print(f"   ℹ| Merge completed: {changed_count} records created or updated.")
    
    # Calculate status and derived fields for modified records
    for wb, rec in db_records.items():
        if not rec.get('changed'):
            continue
            
        ib_time = rec['inbound_scanDate']
        pk_time = rec['Pickup_time']
        fc_time = rec['dispatchNetworkTime']
        ob_time = rec['outbound_scanDate']
        
        # Outbound logic filter:
        # If in Outbound but has no Inbound Time -> mark status = 'Đã rời HUB'
        if ob_time and (not ib_time or ib_time.lower() in ('nan', 'none', '')):
            status = 'Đã rời HUB'
        elif ob_time:
            status = 'Đã rời HUB'
        elif ib_time:
            status = 'Đang trên bãi'
        elif pk_time:
            status = 'Đã lấy hàng'
        elif fc_time:
            status = 'Đã điều phối bưu cục'
        else:
            status = 'Forecast'
            
        rec['status_order'] = status
        
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
                rec['outbound_scanDate'], rec['dispatch_actual'], rec['status_order'], rec['time_ref']
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
                INSERT INTO inventory (
                    waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                    Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                    next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                    outbound_scanDate, dispatch_actual, status_order, time_ref,
                    last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                    dispatch_actual    = excluded.dispatch_actual,
                    status_order       = excluded.status_order,
                    time_ref           = excluded.time_ref,
                    last_updated       = CURRENT_TIMESTAMP
            """, changed_records)
            conn.commit()
            conn.close()
            print(f"   ✅ Đã UPSERT thành công {len(changed_records)} bản ghi thay đổi vào SQLite.")
        except Exception as ex_db:
            print(f"   ❌ Lỗi lưu dữ liệu thay đổi vào SQLite: {ex_db}")

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
    print("\n🚀 Đang push data lên Github Raw...")
    push_json_to_github(df, GH_TOKEN, GH_REPO, GH_DATA_PATH)
    
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
            'countryId': '1', 'size': 1000, 'wayType': '1',
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
    if not args.sync_only:
        tasks.append(("GiamSatPhatHang", lambda: run_giam_sat_phat_hang(session, token_mgr)))

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


if __name__ == "__main__":
    main()