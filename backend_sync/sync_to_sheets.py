import os
import re
import json
import time
import math
import hashlib
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from requests.adapters import HTTPAdapter

# ============================================================
# CONFIG ĐĂNG NHẬP (Đọc từ GitHub Secrets / Environment Variables)
# ============================================================
ACCOUNT    = os.environ.get("SYSTEM_ACCOUNT", "660021")
PASSWORD   = os.environ.get("SYSTEM_PASSWORD", "Tien@giang2395")
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

# ============================================================
# ENDPOINTS (GIỮ NGUYÊN)
# ============================================================
URL_FORECAST       = 'https://gw.jtcargo.com.vn/networkmanagement/omsWaybill/shippingWaybillList'
URL_FORECAST_COUNT = 'https://gw.jtcargo.com.vn/networkmanagement/omsWaybill/shippingWaybillListCount'
URL_SCAN           = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
URL_DISPATCH       = 'https://gw.jtcargo.com.vn/customerplatform/omsOrderDispatch/page'

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

    if total > 0:
        all_data = pull_pages_parallel(fetch_page, total, page_size, label)
    else:
        all_data = pull_pages_sequential(fetch_page, page_size, label)

    return all_data


def pull_scan(session, token_mgr, url, headers, params, base_payload, label=''):
    page_size = int(base_payload.get('size', 1000))

    total = None
    try:
        count_payload = {**base_payload, 'paginationSearchType': 'count', 'size': 1}
        r = auth_post(session, url, token_mgr, headers, params=params,
                      json_body=count_payload, label=f'{label} count')
        t = r.json().get('data', {}).get('total', None)
        total = t if isinstance(t, int) else None
    except Exception as e:
        print(f"   ⚠️ {label} count: {e}")

    def fetch_page(p):
        payload = {**base_payload, 'current': p, 'paginationSearchType': 'list'}
        r = auth_post(session, url, token_mgr, headers, params=params, json_body=payload, label=label)
        return r.json().get('data', {}).get('records', []) or []

    if total is not None:
        all_data = pull_pages_parallel(fetch_page, total, page_size, label)
    else:
        all_data = pull_pages_sequential(fetch_page, page_size, label, total=None, stop_short=True)

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
            d_sortcode = df.set_index('sortcode')['Bưu cục final'].to_dict()
        if 'Bưu cục' in df.columns and 'Bưu cục final' in df.columns:
            d_buucuc = df.set_index('Bưu cục')['Bưu cục final'].to_dict()
        if 'Bưu cục final' in df.columns:
            if 'Tuyến' in df.columns:
                d_tuyen = df.set_index('Bưu cục final')['Tuyến'].to_dict()
            if 'Rank' in df.columns:
                d_rank = df.set_index('Bưu cục final')['Rank'].to_dict()
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
def update_google_sheet(df):
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    
    print(f"\n📊 Bắt đầu cập nhật dữ liệu Google Sheets cho ngày {current_date}...")
    
    df_clean = df.copy()
    df_clean['next_station'] = df_clean['next_station'].astype(str).str.strip().str.upper()
    
    # 1. Tính toán lượng Outbound (Đã rời HUB)
    df_outbound = df_clean[df_clean['status_order'] == 'Đã rời HUB']
    outbound_volumes = df_outbound.groupby('next_station').size().to_dict()
    
    # 2. Tính toán lượng Backlog (Đang trên bãi)
    df_backlog = df_clean[df_clean['status_order'] == 'Đang trên bãi']
    backlog_volumes = df_backlog.groupby('next_station').size().to_dict()
    
    # 3. Kết nối Google Sheet
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        print("❌ Không tìm thấy biến môi trường GOOGLE_SERVICE_ACCOUNT_JSON. Bỏ qua ghi Sheet.")
        return
        
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(SHEET_ID).sheet1
        
        all_rows = sheet.get_all_values()
        if not all_rows:
            print("❌ Google Sheet rỗng.")
            return
            
        headers = all_rows[0]
        
        # Xác định chỉ mục cột (0-based)
        col_zone = headers.index("Zone") if "Zone" in headers else 0
        col_area = headers.index("AreaID") if "AreaID" in headers else 1
        col_name = headers.index("Bưu cục") if "Bưu cục" in headers else 2
        col_vol = headers.index("Volume") if "Volume" in headers else 3
        col_len = headers.index("Dài") if "Dài" in headers else 4
        col_wid = headers.index("Rộng") if "Rộng" in headers else 5
        
        # Ưu tiên tìm Kiện hàng trước, sau đó tới Sức chứa Pallet/Sức chứa
        col_cap = -1
        for cap_header in ["Kiện hàng", "Sức chứa Pallet", "Sức chứa"]:
            if cap_header in headers:
                col_cap = headers.index(cap_header)
                break
        if col_cap == -1:
            col_cap = 6 # Default fallback index
            
        if "Ngày" not in headers:
            headers.append("Ngày")
        if "Loại" not in headers:
            headers.append("Loại")
            
        col_date = headers.index("Ngày")
        col_type = headers.index("Loại")
        
        # Thu thập cấu hình bưu cục tĩnh từ dữ liệu hiện tại
        master_chutes = {}
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
                            "capacity": r[col_cap] if (col_cap < len(r) and r[col_cap].strip()) else "780"
                        }
                        
        print(f"   ℹ️ Đã tải {len(master_chutes)} bưu cục cấu hình từ Sheet.")
        
        # Lọc các dòng cũ: giữ lại các dòng của ngày khác, xóa dòng của ngày hiện tại
        new_rows = [headers]
        for r in all_rows[1:]:
            if len(r) > col_date:
                r_date = r[col_date].strip()
                if r_date and r_date != current_date:
                    while len(r) < len(headers):
                        r.append("")
                    new_rows.append(r)
            else:
                pass
                
        # Tạo dòng mới cho ngày hiện tại với cả 2 loại Outbound & Backlog
        for type_name, vol_map in [("Outbound", outbound_volumes), ("Backlog", backlog_volumes)]:
            for (zone, area_id), info in master_chutes.items():
                name_upper = info["name"].strip().upper()
                vol = vol_map.get(name_upper, 0)
                # Định dạng volume có chấm phân cách hàng nghìn nếu lớn hơn 1000
                vol_str = f"{vol:,}".replace(",", ".") if vol >= 1000 else str(vol)
                
                row = [""] * len(headers)
                row[col_zone] = info["zone"]
                row[col_area] = info["area_id"]
                row[col_name] = info["name"]
                row[col_vol] = vol_str
                row[col_len] = info["dai"]
                row[col_wid] = info["rong"]
                row[col_cap] = info["capacity"]
                row[col_date] = current_date
                row[col_type] = type_name
                
                new_rows.append(row)
                
        # Ghi đè lại Google Sheet
        print(f"   📤 Ghi {len(new_rows) - 1} dòng dữ liệu (bao gồm cả lịch sử) lên Google Sheets...")
        sheet.clear()
        sheet.update(range_name="A1", values=new_rows)
        print("   ✅ Cập nhật Google Sheets thành công!")
        
    except Exception as e:
        print(f"   ❌ Lỗi cập nhật Google Sheets: {e}")


# ================================================================
# MAIN (Run Once)
# ================================================================
def run_once(session, token_mgr):
    now = datetime.now()
    DATE_START = (now - timedelta(days=3)).strftime('%Y-%m-%d') + ' 00:00:00'
    DATE_END   = now.strftime('%Y-%m-%d') + ' 23:59:59'

    print("\n" + "=" * 60)
    print(f"🕐 Bắt đầu : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Range   : {DATE_START} → {DATE_END}")
    print("=" * 60)

    print("\n📋 Load valid.csv...")
    d_sortcode, d_buucuc, d_tuyen, d_rank = load_valid(VALID_FILE)

    print("\n🔐 Kiểm tra token (in-memory)...")
    if not token_mgr.get_token():
        print("❌ Không lấy được token.")
        return

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

    print("\n🚀 Kéo data song song (5 nguồn)...")
    results = {}
    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
        futures = {
            ex.submit(pull_forecast, session, token_mgr, fh, fp): 'forecast',
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, ih, i_params, ip, 'Inbound'): 'inbound',
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, oh, o_params, op, 'Outbound'): 'outbound',
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, bh, b_params, bp, 'Backlog'): 'backlog',
            ex.submit(pull_dispatch, session, token_mgr, dh, dp_cfg): 'dispatch',
        }
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
        df_fc['dispatchNetworkTime'] = ''
        df_fc['updateTime']          = ''
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

        missing_pick = df_all['Pickup_time'].isna() | (df_all['Pickup_time'].astype(str).str.strip() == '')
        has_upd = df_all['_upd_time'].notna() & (df_all['_upd_time'].astype(str).str.strip() != '')
        df_all['Pickup_time'] = df_all['_upd_time'].where(missing_pick & has_upd, df_all['Pickup_time'])

        df_all['updateTime'] = df_all['_upd_time'].where(has_upd, df_all.get('Pickup_time', ''))

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
        sys_status = str(row.get('status_order', '')).strip()
        if sys_status == 'Lấy hàng thất bại':
            sys_status = 'Đã điều phối nhân viên'

        if sys_status in ['Đã điều phối nhân viên', 'Đã điều phối bưu cục']:
            return sys_status

        if row.get('data_source') == 'Dispatch' and sys_status and sys_status not in ('nan', 'None', ''):
            return sys_status

        if row.get('data_source') == 'Backlog':
            if has_value(row.get('outbound_scanDate')):
                return 'Đã rời HUB'
            return 'Đang trên bãi'

        if has_value(row.get('outbound_scanDate')):
            return 'Đã rời HUB'

        if has_value(row.get('inbound_scanDate')):
            return 'Đang trên bãi'

        if has_value(row.get('updateTime')):
            return 'Chưa về HUB'

        if has_value(row.get('dispatchNetworkTime')):
            return 'Đã lấy hàng'

        if sys_status and sys_status not in ('nan', 'None', ''):
            return sys_status

        return ''

    df['status_order'] = df.apply(build_status, axis=1)

    df['Tuyến'] = df['next_station'].map(d_tuyen).fillna('')
    df['Rank']  = df['next_station'].map(d_rank).fillna('')

    col_order = [
        'waybillNo', 'data_source', 'weight',
        'pickNetworkName', 'dispatch_plan',
        'Pickup_time', 'pickup_label', 'Pickup_ontime',
        'dispatchNetworkTime', 'updateTime',
        'next_station', 'Tuyến', 'Rank',
        'inbound_network', 'inbound_scanDate',
        'outbound_scanDate', 'dispatch_actual',
        'status_order'
    ]
    df = df[[c for c in col_order if c in df.columns]]

    # Save to local CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"Inventory_HCMHUB_{now.strftime('%Y%m%d_%H%M')}.csv")
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✅ Đã lưu CSV thô → '{output_file}'")

    _cleanup_old_files(OUTPUT_DIR, keep_file=output_file)
    
    # Cập nhật dữ liệu lên Google Sheets với Lịch sử (Date & Type)
    update_google_sheet(df)


def main():
    session = build_session()
    token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)
    try:
        run_once(session, token_mgr)
    except Exception as e:
        print(f"\n❌ Lỗi thực thi: {e}")


if __name__ == "__main__":
    main()
