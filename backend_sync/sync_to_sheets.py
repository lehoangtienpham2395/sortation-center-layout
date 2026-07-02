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
    statuses = ["Đã rời HUB", "Đã điều phối nhân viên", "Chưa về HUB", "Đang trên bãi", "Đã điều phối bưu cục"]
    
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


def update_inbound_sheets(gc, results, master_chutes):
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
                return
        
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
                
            sheet.update('A1', rows)
            print(f"   ✅ Đã cập nhật Sheet '{sheet_name}' với {len(rows)-1} dòng.")
        except Exception as e:
            print(f"   ❌ Lỗi ghi dữ liệu lên sheet '{sheet_name}': {e}")

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

    # Build reverse lookup map for chutes
    name_to_chute = {}
    for key, chute in master_chutes.items():
        chute_name = str(chute.get('name', '')).strip().upper()
        if chute_name:
            name_to_chute[chute_name] = chute

    rows_to_aggregate = []
    
    # 1. Forecast
    df_fc_raw = pd.DataFrame(results.get('forecast', []))
    if not df_fc_raw.empty:
        for _, r in df_fc_raw.iterrows():
            fc = str(r.get('pickNetworkName', '')).strip()
            waybill = str(r.get('waybillNo', '')).strip()
            w = float(r.get('loadWeight') or 0.0)
            t_ref = r.get('deliveryTime')
            if fc and waybill:
                rows_to_aggregate.append({
                    'fc': fc,
                    'waybill': waybill,
                    'weight': w,
                    'status': 'Forecast',
                    'ib_date': '',
                    'time_ref': t_ref
                })
                
    # 2. Dispatch
    df_dp_raw = pd.DataFrame(results.get('dispatch', []))
    if not df_dp_raw.empty:
        for _, r in df_dp_raw.iterrows():
            fc = str(r.get('pickNetworkName', '')).strip()
            waybill = str(r.get('waybillNo') or r.get('waybillId', '')).strip()
            w = float(r.get('packageChargeWeight') or 0.0)
            status = str(r.get('orderStatusName') or 'Dispatch').strip()
            t_ref = r.get('updateTime') or r.get('dispatchNetworkTime')
            if fc and waybill:
                rows_to_aggregate.append({
                    'fc': fc,
                    'waybill': waybill,
                    'weight': w,
                    'status': status if status != 'nan' else 'Dispatch',
                    'ib_date': '',
                    'time_ref': t_ref
                })

    # 3. Inbound
    df_in_raw = pd.DataFrame(results.get('inbound', []))
    if not df_in_raw.empty:
        for _, r in df_in_raw.iterrows():
            fc = str(r.get('sendSite', '')).strip()
            waybill = str(r.get('waybillNo', '')).strip()
            w = float(r.get('weight') or 0.0)
            ib_date = str(r.get('scanDate', '')).strip()
            if fc and waybill:
                rows_to_aggregate.append({
                    'fc': fc,
                    'waybill': waybill,
                    'weight': w,
                    'status': 'Arrival',
                    'ib_date': ib_date,
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
            
    # Group by fc, status, op_date, and hourly slot
    grouped = {}
    now_vn = datetime.now()
    
    for wb, r in unique_waybills.items():
        fc_name = r['fc']
        status = r['status']
        
        # Inbound map: if inbound scan exists -> "Đã nhập hàng", else corresponding statuses
        if status == 'Arrival' and r['ib_date']:
            status_clean = 'Đã nhập hàng'
            ib_date_str = r['ib_date']
            try:
                dt_ib = pd.to_datetime(ib_date_str)
                ib_hour = dt_ib.strftime('%Y-%m-%d %H:00')
                op_date = get_operating_date(dt_ib)
            except Exception:
                ib_hour = 'N/A'
                op_date = get_operating_date(now_vn)
        else:
            status_clean = status if status in ['Forecast', 'Dispatch', 'Inbound'] else 'Chưa về HUB'
            ib_hour = 'N/A'
            
            # Get op_date from time_ref
            t_ref = r['time_ref']
            if t_ref:
                op_date = get_operating_date(t_ref)
            else:
                op_date = get_operating_date(now_vn)
                
        key = (fc_name, status_clean, op_date, ib_hour)
        if key not in grouped:
            grouped[key] = {'volume': 0, 'weight': 0.0}
        grouped[key]['volume'] += 1
        grouped[key]['weight'] += r['weight']
        
    # Convert grouped to DataFrame without Zone, AreaID, capacity
    final_rows = []
    
    for (fc_name, status, op_date, ib_hour), stats in grouped.items():
        final_rows.append({
            'Bưu cục': fc_name,
            'Trạng thái': status,
            'Volume': stats['volume'],
            'Weight': int(stats['weight']),
            'Ngày vận hành': op_date,
            'Inbound Time': ib_hour
        })
        
    df_inbound_aggregated = pd.DataFrame(final_rows)
    write_sheet("Inbound", df_inbound_aggregated, ["Bưu cục", "Trạng thái", "Volume", "Weight", "Ngày vận hành", "Inbound Time"])

    # 4. Linehaul
    df_lh_raw = pd.DataFrame(results.get('linehaul', []))
    df_lh = pd.DataFrame()
    if not df_lh_raw.empty:
        df_lh['Phiếu nhiệm vụ'] = df_lh_raw['traceCode'].fillna('') if 'traceCode' in df_lh_raw.columns else ''
        df_lh['Phiếu nhiệm vụ con'] = df_lh_raw['traceSubCode'].fillna('') if 'traceSubCode' in df_lh_raw.columns else ''
        df_lh['sendTime'] = df_lh_raw['sendTime'].fillna('') if 'sendTime' in df_lh_raw.columns else ''
        df_lh['loadingEndTime'] = df_lh_raw['loadingEndTime'].fillna('') if 'loadingEndTime' in df_lh_raw.columns else ''
        df_lh['nextNetworkName'] = df_lh_raw['nextNetworkName'].fillna('') if 'nextNetworkName' in df_lh_raw.columns else ''
        df_lh['unloadingStartTime'] = df_lh_raw['unloadingStartTime'].fillna('') if 'unloadingStartTime' in df_lh_raw.columns else ''
        df_lh['unloadingEndTime'] = df_lh_raw['unloadingEndTime'].fillna('') if 'unloadingEndTime' in df_lh_raw.columns else ''
        df_lh['unloadingBillPiece'] = df_lh_raw['unloadingBillPiece'].fillna(0) if 'unloadingBillPiece' in df_lh_raw.columns else 0
        df_lh['unloadingWeight'] = df_lh_raw['unloadingWeight'].fillna(0) if 'unloadingWeight' in df_lh_raw.columns else 0
    write_sheet("Linehaul", df_lh, ["Phiếu nhiệm vụ", "Phiếu nhiệm vụ con", "sendTime", "loadingEndTime", "nextNetworkName", "unloadingStartTime", "unloadingEndTime", "unloadingBillPiece", "unloadingWeight"])


def update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, current_date_str, results=None):
    print(f"\n📊 Bắt đầu cập nhật dữ liệu Google Sheets...")
    
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
            if 'status_order' in df.columns:
                df_bl_real = df[df['status_order'] == 'Đang trên bãi'].copy()
                if not df_bl_real.empty:
                    df_bl_real['next_station_upper'] = df_bl_real['next_station'].astype(str).str.strip().str.upper()
                    backlog_volumes = df_bl_real.groupby('next_station_upper').agg(
                        volume=('waybillNo', 'size'),
                        weight=('weight', 'sum')
                    ).to_dict(orient='index')
            update_backlog_sheet(gc, master_chutes, backlog_volumes, current_date_str)
            
        # 3. Update Inventory Sheet (Realtime Pivot)
        if run_backlog_inv:
            inventory_volumes = {}
            if 'status_order' in df.columns:
                df_inv = df.copy()
                df_inv['next_station_upper'] = df_inv['next_station'].astype(str).str.strip().str.upper()
                df_inv['status_upper'] = df_inv['status_order'].astype(str).str.strip()
                inventory_volumes = df_inv.groupby(['next_station_upper', 'status_upper']).agg(
                    volume=('waybillNo', 'size'),
                    weight=('weight', 'sum')
                ).to_dict(orient='index')
            update_inventory_sheet(gc, master_chutes, inventory_volumes, current_date_str)
            
        # 4. Update Inbound Sheets (aggregated Inbound + raw Linehaul)
        if results:
            update_inbound_sheets(gc, results, master_chutes)
            
    except Exception as e:
        print(f"   ❌ Lỗi cập nhật Google Sheets: {e}")

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
        hour = now.hour
        # Khung giờ chốt ca: 06:00 - 06:59
        if hour == 6:
            print("⏰ Khung giờ chốt ca (6:00 AM VN) -> Chạy tất cả các mô-đun (Outbound, Backlog, Inventory)")
            DATE_START = (now - timedelta(days=2)).strftime('%Y-%m-%d') + ' 06:00:00'
            DATE_END   = now.strftime('%Y-%m-%d %H:%M:%S')  # Query up to current second
            run_outbound = True
            run_backlog_inv = True
        # Khung giờ realtime: 13:00 - 05:59 sáng hôm sau
        elif hour >= 13 or hour <= 5:
            print(f"⏰ Khung giờ realtime ({hour}:00 VN) -> Chạy cả Outbound để lọc Backlog")
            DATE_START = (now - timedelta(days=2)).strftime('%Y-%m-%d') + ' 06:00:00'
            DATE_END   = now.strftime('%Y-%m-%d %H:%M:%S')  # Query up to current second
            run_outbound = True
            run_backlog_inv = True
        else:
            print(f"💤 Ngoài khung giờ hoạt động ({hour}:00 VN). Tự động thoát.")
            return

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
            ex.submit(pull_scan, session, token_mgr, URL_SCAN, lh_h, lh_params, lh_p, 'Linehaul'): 'linehaul',
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
    update_google_sheet(df, outbound_volumes_grouped, target_dates, run_outbound, run_backlog_inv, now.strftime('%Y-%m-%d'), results)


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


if __name__ == "__main__":
    main()
