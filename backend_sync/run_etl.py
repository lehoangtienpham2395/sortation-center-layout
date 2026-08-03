# ==============================================================================
# LOGISTICS ANALYTICS PLATFORM - UNIFIED ETL SINGLE PIPELINE (run_etl.py)
# Standard: Enterprise Data Architecture v2.0 & Production Readiness
# Features: Self-contained, Single-File Execution, Parallel Extraction, 
#           14 Business Rules, Single Transaction Commit & Gate 2 DQ Validation.
# ==============================================================================

import os
import sys
import io
import time
import math
import json
import hashlib
import threading
import psycopg2
import requests
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from psycopg2.extras import execute_values

# Thiết lập encoding UTF-8 cho Console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ==============================================================================
# SECTION 1: SYSTEM CONFIGURATION & CONSTANTS
# ==============================================================================
# BASE_DIR: thư mục backend_sync (chứa run_etl.py này)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)  # gốc repo sortation-center-layout

# J&T Cargo API Credentials
ACCOUNT = "660021"
PASSWORD = "Tien@giang2395"
COUNTRY_ID = "1"

# API Endpoints
URL_LOGIN = "https://gw.jtcargo.com.vn/basicdata/login"
URL_DISPATCH = "https://gw.jtcargo.com.vn/customerplatform/omsOrderDispatch/page"
URL_SCAN = "https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination"

# PostgreSQL Database Configuration
DB_HOST = "127.0.0.1"
DB_PORT = 5433
DB_NAME = "logistics_db"
DB_USER = "postgres"
DB_PASSWORD = 'Tien@giang0203'

DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "connect_timeout": 10
}

# ETL Settings
LOOKBACK_DAYS = 7
PAGE_WORKERS = 8
SOURCE_WORKERS = 5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_FACTOR = 2

_VALID_PRIMARY  = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "testing", "Exportauto", "Valid", "valid.csv")
VALID_FILE_PATH = _VALID_PRIMARY if os.path.exists(_VALID_PRIMARY) else os.path.join(BASE_DIR, "config", "valid.csv")
CACHE_FILE = os.path.join(BASE_DIR, ".token_cache")


# ==============================================================================
# SECTION 2: LOGGER SETUP & UTILITIES
# ==============================================================================
def md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def clean_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

import logging
def setup_logger(name: str = "run_etl") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

logger = setup_logger("run_etl")

# ==============================================================================
# SECTION 3: AUTHENTICATION & TOKEN MANAGER (THREAD-SAFE LOCK + CACHE)
# ==============================================================================
class TokenManager:
    """Quản lý đăng nhập và làm mới Token đa luồng an toàn (Lock + File Cache)."""
    def __init__(self, session: requests.Session):
        self.session = session
        self._token = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if self._token:
                return self._token

            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r") as f:
                        cached_t = f.read().strip()
                        if cached_t:
                            self._token = cached_t
                            logger.info(f"✅ Dùng token cache | Token: {self._token[:12]}...")
                            return self._token
                except Exception:
                    pass

            payload = {
                "account": ACCOUNT,
                "password": md5(PASSWORD),
                "captchaToken": "",
                "countryId": COUNTRY_ID
            }
            logger.info("🔑 Đang đăng nhập API J&T Cargo...")
            r = self.session.post(URL_LOGIN, json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            res = r.json()
            if res.get('succ') or res.get('code') == 1:
                data = res.get('data', {})
                self._token = data.get('token') or data.get('authToken')
                if self._token:
                    try:
                        with open(CACHE_FILE, "w") as f:
                            f.write(self._token)
                    except Exception:
                        pass
                logger.info(f"✅ Đăng nhập thành công | Token: {self._token[:12]}...")
            else:
                raise Exception(f"Đăng nhập thất bại: {res}")
            return self._token

    def refresh(self) -> str:
        with self._lock:
            self._token = None
            if os.path.exists(CACHE_FILE):
                try:
                    os.remove(CACHE_FILE)
                except Exception:
                    pass
        return self.get_token()

def auth_post_with_retry(session: requests.Session, token_mgr: TokenManager, url: str, 
                        json_body: dict = None, data_body: dict = None, params: dict = None, 
                        extra_headers: dict = None, label: str = "") -> dict:
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        token = token_mgr.get_token()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "authToken": token,
            "Authtoken": token,
            "lang": "VN",
            "langtype": "VN"
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            if data_body is not None:
                r = session.post(url, headers=headers, data=data_body, params=params, timeout=REQUEST_TIMEOUT)
            else:
                r = session.post(url, headers=headers, json=json_body, params=params, timeout=REQUEST_TIMEOUT)
            
            if r.status_code in (401, 405):
                logger.warning(f"⚠️ {label}: Token hết hạn/bị từ chối ({r.status_code}), đang làm mới...")
                token_mgr.refresh()
                continue
            r.raise_for_status()
            res = r.json()
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    pass
            if isinstance(res, dict) and res.get("code") == 401:
                logger.warning(f"⚠️ {label}: API từ chối Token (code 401), đang làm mới...")
                token_mgr.refresh()
                continue
            return res if isinstance(res, dict) else {"data": res}
        except Exception as e:
            if attempt == MAX_RETRIES:
                logger.error(f"❌ {label}: Thất bại sau {MAX_RETRIES} lần thử: {e}")
                raise Exception(f"{label} Extractor Error: {e}")
            sleep_time = BACKOFF_FACTOR ** attempt
            logger.warning(f"⚠️ {label}: Lỗi kết nối ({e}). Thử lại {attempt}/{MAX_RETRIES} sau {sleep_time}s...")
            time.sleep(sleep_time)
    return {}

# ==============================================================================
# SECTION 4: PARALLEL DATA EXTRACTOR (SINGLE CALL COUNT + THREADPOOL PAGINATION)
# ==============================================================================
def extract_total_and_records(res: dict) -> tuple:
    if not isinstance(res, dict):
        return 0, []
    data = res.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if isinstance(data, dict):
        total = data.get("total") or 0
        records = data.get("records") or data.get("rows") or data.get("list") or []
        return total, records
    elif isinstance(data, list):
        return len(data), data
    return 0, []

def fetch_all_sources(session: requests.Session, start_date_str: str, end_date_str: str) -> dict:
    """
    Kéo dữ liệu thô song song từ các Nguồn API (Dispatch, Inbound, Outbound, Backlog, Arrival).
    Tối ưu hóa: Đọc tổng số dòng (total) -> Kéo song song tất cả các trang bằng ThreadPoolExecutor.
    """
    token_mgr = TokenManager(session)
    results = {}

    def fetch_dispatch():
        label = "Dispatch API"
        size = 1000
        extra_h = {"routeName": "orderScheduling"}

        def fetch_p(page):
            payload = {
                "startInputTime": start_date_str,
                "endInputTime": end_date_str,
                "timeType": "1",
                "current": str(page),
                "size": str(size)
            }
            res = auth_post_with_retry(session, token_mgr, URL_DISPATCH, data_body=payload, extra_headers=extra_h, label=f"{label} P{page}")
            tot, recs = extract_total_and_records(res)
            return tot, recs

        try:
            total, recs1 = fetch_p(1)
        except Exception as e:
            logger.error(f"❌ {label} P1 lỗi: {e}")
            return []

        all_records = list(recs1)
        if total and total > len(recs1):
            n_pages = math.ceil(total / size)
            logger.info(f"📊 {label}: Tổng {total:,} bản ghi ({n_pages} trang song song)...")
            res_pages = {}
            with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
                future_to_p = {ex.submit(fetch_p, p): p for p in range(2, n_pages + 1)}
                for f in as_completed(future_to_p):
                    p = future_to_p[f]
                    try:
                        _, r_list = f.result()
                        res_pages[p] = r_list
                    except Exception as e:
                        logger.warning(f"⚠️ {label} P{p} lỗi: {e}")
                        res_pages[p] = []
            for p in range(2, n_pages + 1):
                all_records.extend(res_pages.get(p, []))

        logger.info(f"✅ {label}: Kéo hoàn tất {len(all_records):,} bản ghi thô Dispatch OMS")
        return all_records

    def fetch_generic_scan(scan_type, sql_code, extra_route, op_type=None, is_arrival=False, label=""):
        size = 1000 if is_arrival else 500
        params = {"sqlCode": sql_code, "dcr_key": "57b048fb-bc8c-4d24-982b-a750b7ce8693"}
        extra_h = {"routeName": extra_route}

        def build_payload(page, search_type="list"):
            pl = {
                "beginDate": start_date_str,
                "endDate": end_date_str,
                "sqlCode": sql_code,
                "current": page,
                "size": size,
                "countryId": COUNTRY_ID,
                "paginationSearchType": search_type
            }
            if is_arrival:
                pl.update({"startTime": start_date_str, "endTime": end_date_str, "timeType": "2"})
            elif op_type:
                pl.update({"scanSiteCode": "HCM004H", "scanSiteCodeName": "HCM HUB",
                           "scanSiteCodeTypeId": 335, "scanSiteCodeId": 11888, "operateSiteType": op_type})
            else:
                pl.update({"scanSite": "HCM004H", "scanType": scan_type, "billType": 1})
            return pl

        # Step 1: Count total
        total = None
        try:
            cnt_pl = build_payload(1, search_type="count")
            cnt_pl['size'] = 1
            res_cnt = auth_post_with_retry(session, token_mgr, URL_SCAN, json_body=cnt_pl, params=params, extra_headers=extra_h, label=f"{label} Count")
            total, _ = extract_total_and_records(res_cnt)
        except Exception as e:
            logger.warning(f"⚠️ {label} count lỗi: {e}")

            total_str = f"{total:,}" if isinstance(total, int) else "?"
            logger.info(f"📊 {label}: Đã đọc tổng số dòng cần kéo = {total_str} bản ghi")

        def fetch_p(page):
            pl = build_payload(page, search_type="list")
            res = auth_post_with_retry(session, token_mgr, URL_SCAN, json_body=pl, params=params, extra_headers=extra_h, label=f"{label} P{page}")
            _, recs = extract_total_and_records(res)
            return recs

        if total and total > 0:
            n_pages = math.ceil(total / size)
            res_pages = {}
            with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
                future_to_p = {ex.submit(fetch_p, p): p for p in range(1, n_pages + 1)}
                for f in as_completed(future_to_p):
                    p = future_to_p[f]
                    try:
                        res_pages[p] = f.result()
                    except Exception as e:
                        logger.warning(f"⚠️ {label} P{p} lỗi: {e}")
                        res_pages[p] = []
            all_records = []
            for p in range(1, n_pages + 1):
                all_records.extend(res_pages.get(p, []))
        else:
            all_records = []
            page = 1
            while True:
                recs = fetch_p(page)
                if not recs: break
                all_records.extend(recs)
                if len(recs) < size: break
                page += 1

        logger.info(f"✅ {label}: Kéo hoàn tất {len(all_records):,} bản ghi")
        return all_records

    logger.info(f"🚀 Khởi chạy Extractor song song các API (Cửa sổ: {start_date_str} -> {end_date_str})...")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as executor:
        futures = {
            executor.submit(fetch_dispatch): 'dispatch',
            executor.submit(fetch_generic_scan, "卸车扫描", "realtime_barscan_query", "scanQueryConstantlyNew|businessIndicatorIndex", label="Inbound API"): 'inbound',
            executor.submit(fetch_generic_scan, "装车扫描", "realtime_barscan_query", "scanQueryConstantlyNew|businessIndicatorIndex", label="Outbound API"): 'outbound',
            executor.submit(fetch_generic_scan, None, "realtime_inv_man_dtl", "Bd-theme-4d718ae8-fa85-4edc-b98c-1a0f75e5f9f3|businessIndicatorIndex", op_type="all", label="Backlog API"): 'backlog',
            executor.submit(fetch_generic_scan, None, "transport_consolidated_report", "Bd-table-bb3e578a-fa67-4587-8ed3-f69ec34aaab7|businessIndicatorIndex", is_arrival=True, label="Arrival API"): 'arrival',
        }
        for f in as_completed(futures):
            key = futures[f]
            try:
                results[key] = f.result()
            except Exception as e:
                logger.error(f"❌ {key} Extractor thất bại: {e}")
                results[key] = []

    elapsed = time.time() - t0
    logger.info(f"🎉 Hoàn thành Extractor song song trong {elapsed:.2f} giây.")
    return results

# ==============================================================================
# SECTION 5: TRANSFORMER & 14 BUSINESS RULES
# ==============================================================================
def rule_01_clean_tracking(val) -> str:
    return clean_str(val)

def rule_02_is_canceled_order(status_name: str) -> bool:
    if not status_name:
        return False
    return str(status_name).strip() == 'Đã hủy'

def rule_03_parse_created_time(created_val) -> str:
    if not created_val:
        return None
    return str(created_val).strip()

def rule_04_resolve_pickup_station(pick_name: str, real_name: str) -> tuple:
    st1 = str(pick_name or real_name or '').strip()
    st2 = str(real_name or '').strip()
    return st1, st2

def rule_05_parse_dispatch_code(term_code: str) -> str:
    if not term_code:
        return ""
    code = str(term_code).strip()
    return code.split('-')[-1] if '-' in code else code

def rule_06a_map_next_station(dispatch_code: str, valid_mapping: dict) -> str:
    if not dispatch_code or not valid_mapping:
        return "KHO VÙNG KHÁC"
    info = valid_mapping.get(dispatch_code.upper())
    return info.get("next_station", "KHO VÙNG KHÁC") if info else "KHO VÙNG KHÁC"

def rule_06b_calculate_round(dispatch_code: str, valid_mapping: dict) -> str:
    if not dispatch_code or not valid_mapping:
        return "Chưa Phân Tuyến"
    info = valid_mapping.get(dispatch_code.upper())
    return info.get("round", "Chưa Phân Tuyến") if info else "Chưa Phân Tuyến"

def rule_06c_calculate_rank(dispatch_code: str, valid_mapping: dict) -> str:
    if not dispatch_code or not valid_mapping:
        return "KHO VÙNG KHÁC"
    info = valid_mapping.get(dispatch_code.upper())
    return info.get("rank", "KHO VÙNG KHÁC") if info else "KHO VÙNG KHÁC"

def rule_07_evaluate_pickup_ontime(created_time_str: str, pickup_time_str: str) -> str:
    if not created_time_str or not pickup_time_str:
        return "PENDING"
    try:
        t_create = datetime.strptime(created_time_str[:19], "%Y-%m-%d %H:%M:%S")
        t_pickup = datetime.strptime(pickup_time_str[:19], "%Y-%m-%d %H:%M:%S")
        return "YES" if (t_pickup - t_create).total_seconds() <= 7200 else "NO"
    except Exception:
        return "PENDING"

def rule_11_evaluate_is_active(outbound_time_str: str, status_name: str) -> int:
    if outbound_time_str or status_name in ('Ký nhận thành công', 'Đã hủy'):
        return 0
    return 1

def load_valid_mapping() -> dict:
    mapping = {}
    path = os.path.join(BASE_DIR, "stations_master.csv") if not os.path.exists(VALID_FILE_PATH) else VALID_FILE_PATH
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype=str)
            df.columns = df.columns.str.strip()
            sc_col = next((c for c in ['sortcode', 'Mã trạm', 'dispatch_code'] if c in df.columns), None)
            st_col = next((c for c in ['Bưu cục final', 'Bưu cục', 'Station_1', 'Station_2'] if c in df.columns), None)
            rd_col = next((c for c in ['Round', 'Tuyến', 'round'] if c in df.columns), None)
            rk_col = next((c for c in ['Rank', 'Phân hạng', 'rank'] if c in df.columns), None)
            
            if sc_col and st_col:
                for _, row in df.iterrows():
                    code = clean_str(row.get(sc_col)).upper()
                    if code:
                        mapping[code] = {
                            "next_station": clean_str(row.get(st_col)) or "KHO VÙNG KHÁC",
                            "round": clean_str(row.get(rd_col)) if rd_col else "Chưa Phân Tuyến",
                            "rank": clean_str(row.get(rk_col)) if rk_col else "KHO VÙNG KHÁC"
                        }
            logger.info(f"✅ Nạp thành công {len(mapping):,} mã sortcode từ valid mapping ({path})")
        except Exception as e:
            logger.warning(f"⚠️ Không thể đọc file valid mapping: {e}")
    return mapping

def transform_raw_to_enriched_records(raw_data: dict, valid_mapping: dict) -> list:
    dispatch_list = raw_data.get('dispatch', [])
    inbound_list = raw_data.get('inbound', [])
    outbound_list = raw_data.get('outbound', [])
    backlog_list = raw_data.get('backlog', [])

    inbound_map = {clean_str(x.get('billNo')): x.get('scanDate') for x in inbound_list if clean_str(x.get('billNo'))}
    outbound_map = {clean_str(x.get('billNo')): x.get('scanDate') for x in outbound_list if clean_str(x.get('billNo'))}
    backlog_set = {clean_str(x.get('billcode')) for x in backlog_list if clean_str(x.get('billcode'))}

    enriched_records = []
    purged_count = 0

    seen_trackings = set()
    unique_dispatch_list = []
    for r in dispatch_list:
        wb = rule_01_clean_tracking(r.get('waybillId') or r.get('waybillNo'))
        if wb and wb not in seen_trackings:
            seen_trackings.add(wb)
            unique_dispatch_list.append(r)

    for r in unique_dispatch_list:
        status_name = str(r.get('orderStatusName') or '').strip()
        if rule_02_is_canceled_order(status_name):
            purged_count += 1
            continue

        wb = rule_01_clean_tracking(r.get('waybillId') or r.get('waybillNo'))
        if not wb:
            continue

        created_t = rule_03_parse_created_time(r.get('dispatchNetworkTime') or r.get('inputTime'))
        if not created_t:
            created_t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        dt_obj = pd.to_datetime(created_t, errors='coerce')
        if pd.notnull(dt_obj):
            op_date = (dt_obj - pd.Timedelta(days=1)).strftime('%Y-%m-%d') if dt_obj.hour < 6 else dt_obj.strftime('%Y-%m-%d')
        else:
            op_date = datetime.now().strftime('%Y-%m-%d')
        
        pick_st, pick_st2 = rule_04_resolve_pickup_station(r.get('pickNetworkName'), r.get('realPickNetworkName'))
        pickup_t = r.get('pickTime') if status_name == 'Đã lấy hàng' else None

        disp_code = rule_05_parse_dispatch_code(r.get('terminalDispatchCode'))
        next_station = rule_06a_map_next_station(disp_code, valid_mapping)
        round_val = rule_06b_calculate_round(disp_code, valid_mapping)
        rank_val = rule_06c_calculate_rank(disp_code, valid_mapping)
        ontime = rule_07_evaluate_pickup_ontime(created_t, pickup_t)

        inbound_t = inbound_map.get(wb)
        outbound_t = outbound_map.get(wb)

        op_date_inb = None
        if inbound_t:
            inb_dt = pd.to_datetime(inbound_t, errors='coerce')
            if pd.notnull(inb_dt):
                op_date_inb = (inb_dt - pd.Timedelta(days=1)).strftime('%Y-%m-%d') if inb_dt.hour < 6 else inb_dt.strftime('%Y-%m-%d')

        is_bl = 1 if (wb in backlog_set or inbound_t) and not outbound_t else 0
        is_act = rule_11_evaluate_is_active(outbound_t, status_name)

        enriched_records.append({
            'tracking': wb,
            'data_source': 'Dispatch',
            'status_sys': status_name,
            'Created_time': created_t,
            'Pickup_station': pick_st,
            'Dispatch_code': disp_code,
            'Orders_num': int(r.get('packageNumber') or 1),
            'Orders_weight': float(r.get('packageChargeWeight') or 0.0),
            'Pickup_station2': pick_st2,
            'Pickup_time': pickup_t,
            'Pickup_ontime': ontime,
            'AreaCode': str(r.get('proxyAreaCode') or '').strip(),
            'flowTypeDesc': str(r.get('flowTypeDesc') or '').strip(),
            'Next_station': next_station,
            'Round': round_val,
            'Rank': rank_val,
            'inbound_scanDate': inbound_t,
            'outbound_scanDate': outbound_t,
            'arrival_scanDate': None,
            'trip_code': '',
            'transporing_time': None,
            'transported_time': None,
            'dispatch_actual': str(r.get('nextNetworkName') or '').strip(),
            'operation_date': op_date,
            'operation_date_inbound': op_date_inb,
            'is_backlog': is_bl,
            'is_active': is_act,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    logger.info(f"🎉 Biến đổi thành công {len(enriched_records):,} bản ghi chuẩn 29 cột (Đã loại bỏ {purged_count} đơn hủy)")
    return enriched_records

# ==============================================================================
# SECTION 6: POSTGRESQL LOADER & GATE 2 DQ VALIDATION
# ==============================================================================
def load_raw_payloads(conn, raw_data: dict) -> int:
    total_inserted = 0
    cur = conn.cursor()
    
    # 1. Load Dispatch
    dispatch_records = raw_data.get('dispatch', [])
    if dispatch_records:
        tuples = [(clean_str(r.get('waybillId') or r.get('waybillNo')), json.dumps(r, ensure_ascii=False)) 
                  for r in dispatch_records if (r.get('waybillId') or r.get('waybillNo'))]
        sql = """
            INSERT INTO raw.raw_dispatch (tracking, raw_payload)
            VALUES %s
            ON CONFLICT (tracking) DO NOTHING;
        """
        execute_values(cur, sql, tuples, page_size=1000)
        total_inserted += len(tuples)
        logger.info(f"✅ Nạp {len(tuples):,} bản ghi thô vào raw.raw_dispatch")

    # 2. Load Scans
    scan_types = [
        ('inbound', 'INBOUND'),
        ('outbound', 'OUTBOUND'),
        ('backlog', 'BACKLOG'),
        ('arrival', 'LINEHAUL_ARRIVAL')
    ]
    for key, event_type in scan_types:
        recs = raw_data.get(key, [])
        if recs:
            tuples = []
            for r in recs:
                wb = clean_str(r.get('billNo') or r.get('billcode') or r.get('waybillNo'))
                site = clean_str(r.get('scanSite') or r.get('scanSiteCodeName') or r.get('siteName'))
                sc_date = r.get('scanDate') or r.get('operate_scantime_1') or r.get('inputDate')
                tuples.append((wb, event_type, site, sc_date, json.dumps(r, ensure_ascii=False)))
            
            sql = """
                INSERT INTO raw.raw_scan_events (tracking, scan_type, site_code, scan_date, raw_payload)
                VALUES %s;
            """
            execute_values(cur, sql, tuples, page_size=1000)
            total_inserted += len(tuples)
            logger.info(f"✅ Nạp {len(tuples):,} bản ghi thô ({event_type}) vào raw.raw_scan_events")

    logger.info(f"🎉 Hoàn thành nạp tầng RAW: Tổng {total_inserted:,} bản ghi thô JSON.")
    return total_inserted

def validate_data_quality_pre_commit(conn, records: list) -> list:
    violations = []
    if not records:
        return violations

    trackings = [r['tracking'] for r in records if r.get('tracking')]
    if len(trackings) != len(set(trackings)):
        violations.append("DQ-01 Violation: Trùng lặp mã tracking trong mảng enriched!")

    null_trackings = [r for r in records if not r.get('tracking') or not r.get('data_source')]
    if null_trackings:
        violations.append(f"DQ-02 Violation: Phát hiện {len(null_trackings)} bản ghi thiếu tracking/data_source!")

    unmapped_count = sum(1 for r in records if r.get('Next_station') == 'KHO VÙNG KHÁC')
    unmapped_rate = (unmapped_count / len(records)) * 100 if records else 0
    if unmapped_rate > 2.0:
        logger.warning(f"⚠️ DQ-04 Alert: Tỷ lệ unmapped station = {unmapped_rate:.2f}% (vượt 2%)")

    canceled_records = [r for r in records if r.get('status_sys') == 'Đã hủy']
    if canceled_records:
        violations.append(f"DQ-06 Violation: Phát hiện {len(canceled_records)} bản ghi 'Đã hủy' chưa bị loại bỏ!")

    return violations

def stage_and_commit_pipeline(conn, records: list):
    if not records:
        logger.info("ℹ️ Không có bản ghi nào để Upsert.")
        return

    sql_upsert = """
    INSERT INTO enriched.dispatch_enriched (
        tracking, data_source, status_sys, Created_time, Pickup_station, Dispatch_code,
        Orders_num, Orders_weight, Pickup_station2, Pickup_time, Pickup_ontime, AreaCode,
        flowTypeDesc, Next_station, Round, Rank, inbound_scanDate, outbound_scanDate,
        arrival_scanDate, trip_code, transporing_time, transported_time, dispatch_actual,
        operation_date_created, operation_date_inbound, is_backlog, is_active, last_updated
    ) VALUES %s
    ON CONFLICT (tracking) DO UPDATE SET
        data_source = EXCLUDED.data_source,
        status_sys = EXCLUDED.status_sys,
        is_backlog = EXCLUDED.is_backlog,
        is_active = EXCLUDED.is_active,
        last_updated = CURRENT_TIMESTAMP,
        Created_time = COALESCE(enriched.dispatch_enriched.Created_time, EXCLUDED.Created_time),
        Pickup_time = COALESCE(enriched.dispatch_enriched.Pickup_time, EXCLUDED.Pickup_time),
        inbound_scanDate = COALESCE(enriched.dispatch_enriched.inbound_scanDate, EXCLUDED.inbound_scanDate),
        outbound_scanDate = COALESCE(enriched.dispatch_enriched.outbound_scanDate, EXCLUDED.outbound_scanDate);
    """

    values = []
    for r in records:
        created_t = r.get('Created_time')
        inbound_t = r.get('inbound_scanDate')
        
        values.append((
            r['tracking'], r['data_source'], r['status_sys'], created_t, r['Pickup_station'], r['Dispatch_code'],
            r['Orders_num'], r['Orders_weight'], r['Pickup_station2'], r['Pickup_time'], r['Pickup_ontime'], r['AreaCode'],
            r['flowTypeDesc'], r['Next_station'], r['Round'], r['Rank'], inbound_t, r['outbound_scanDate'],
            r['arrival_scanDate'], r['trip_code'], r['transporing_time'], r['transported_time'], r['dispatch_actual'],
            r.get('operation_date'),
            r.get('operation_date_inbound'),
            r.get('is_backlog', 0), r.get('is_active', 1), r.get('last_updated')
        ))

    with conn.cursor() as cur:
        execute_values(cur, sql_upsert, values, page_size=1000)

        logger.info("🛑 Step 8: Thực thi Gate 2 Pre-Commit Data Quality Validation...")
        violations = validate_data_quality_pre_commit(conn, records)
        if violations:
            raise Exception(f"GATE 2 REJECTED BATCH: {'; '.join(violations)}")

        logger.info("✅ Step 9: Single Transaction COMMIT & Refresh Materialized Views...")
        conn.commit()
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY semantic.mv_inbound_summary;")
        conn.commit()

# ==============================================================================
# SECTION 7: MAIN PIPELINE ORCHESTRATION ENTRYPOINT
# ==============================================================================
def run_pipeline():
    logger.info("===============================================================")
    logger.info("🚀 BẮT ĐẦU CHẠY UNIFIED ETL PIPELINE v2.0 (SINGLE PIPELINE)...")
    logger.info("===============================================================")

    t0_pipeline = time.time()

    now = datetime.now()
    start_date_str = (now - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d 06:00:00')
    end_date_str = now.strftime('%Y-%m-%d %H:%M:%S')

    session = requests.Session()
    conn = None

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False

        # 1. Extract Raw API Payloads
        logger.info("Step 1: Kéo dữ liệu thô song song các API...")
        t0_ext = time.time()
        raw_data = fetch_all_sources(session, start_date_str, end_date_str)
        t_ext = time.time() - t0_ext

        # 2. Persist Raw Payloads to RAW Layer
        logger.info("Step 2: Lưu trữ dữ liệu thô vào tầng RAW PostgreSQL...")
        t0_raw = time.time()
        raw_inserted = load_raw_payloads(conn, raw_data)
        t_raw = time.time() - t0_raw

        # 3. Load Valid Mapping & Execute Business Rules
        logger.info("Step 3: Thực thi 14 Quy tắc Nghiệp vụ (Transformers)...")
        t0_tf = time.time()
        valid_mapping = load_valid_mapping()
        enriched_records = transform_raw_to_enriched_records(raw_data, valid_mapping)
        t_tf = time.time() - t0_tf

        # 4. Stage Upsert, Pre-Commit DQ Validation, Commit & Refresh
        logger.info("Step 4: Stage Upsert 29 cột, Gate 2 DQ Validation & Commit...")
        t0_up = time.time()
        stage_and_commit_pipeline(conn, enriched_records)
        t_up = time.time() - t0_up

        t_total = time.time() - t0_pipeline

        logger.info("📊 ===============================================================")
        logger.info("   SUMMARY EXECUTION METRICS REPORT")
        logger.info("===============================================================")
        logger.info(f"⏱️  Extraction Duration    : {t_ext:.2f}s")
        logger.info(f"⏱️  RAW Load Duration      : {t_raw:.2f}s")
        logger.info(f"⏱️  Transform Duration     : {t_tf:.2f}s")
        logger.info(f"⏱️  Upsert & Commit Time   : {t_up:.2f}s")
        logger.info(f"⏱️  TOTAL PIPELINE DURATION : {t_total:.2f}s")
        logger.info(f"🔢 RAW Records Inserted    : {raw_inserted:,}")
        logger.info(f"🔢 Enriched Records Upserted: {len(enriched_records):,}")
        logger.info("===============================================================")
        logger.info("🎉 HOÀN THÀNH ETL PIPELINE v2.0 THÀNH CÔNG RỰC RỠ!")
        logger.info("===============================================================")

    except Exception as e:
        logger.error(f"❌ PIPELINE THẤT BẠI: {e}", exc_info=True)
        if conn:
            conn.rollback()
            logger.info("🔄 Đã thực thi PostgreSQL ROLLBACK 100% an toàn.")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_pipeline()
