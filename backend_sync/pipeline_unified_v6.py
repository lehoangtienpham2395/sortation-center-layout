import os, sys, io, re, json, time, math, hashlib, threading
import requests, pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter

try:
    import pg8000.native
except ImportError:
    pg8000 = None

# ============================================================
# WINDOWS UNICODE FIX
# ============================================================
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
    except Exception:
        pass

# ============================================================
# CONFIG
# ============================================================
ACCOUNT      = os.environ.get('SYSTEM_ACCOUNT',  '').strip() or '660021'
PASSWORD     = os.environ.get('SYSTEM_PASSWORD', '').strip() or 'Tien@giang2299'
ARR_ACCOUNT  = '660085'
ARR_PASSWORD = '246@Hoang'
COUNTRY_ID   = '1'

LOGIN_URL         = 'https://gw.jtcargo.com.vn/basicdata/login'
URL_DISPATCH      = 'https://gw.jtcargo.com.vn/customerplatform/omsOrderDispatch/page'
URL_SCAN          = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
URL_LINEHAUL_OPS  = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryTraceSubForPage'
URL_SHUTTLE_TRACK = 'https://gw.jtcargo.com.vn/transportation/tmsBranchTrackingDetail/page'
URL_FORECAST      = 'https://gw.jtcargo.com.vn/networkmanagement/omsWaybill/shippingWaybillList'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_cfg_candidates = [
    r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid',
    r'C:\Users\lehoa\OneDrive\Desktop\testing\config',
    r'C:\Users\lehoa\OneDrive\Desktop\testing',
    os.path.join(BASE_DIR, 'config'),
    os.path.join(BASE_DIR, 'backend_sync', 'config'),
    os.path.join(BASE_DIR, 'sortation-center-layout', 'backend_sync', 'config'),
    os.path.abspath('.'),
    os.path.abspath('backend_sync'),
    os.path.abspath('data')
]

def find_config_file(filename):
    for d in _cfg_candidates:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return ''

CONFIG_DIR  = next((p for p in _cfg_candidates if os.path.exists(os.path.join(p, 'inboundheaders.json'))), _cfg_candidates[0])
VALID_FILE  = find_config_file('valid.csv') or os.path.join(CONFIG_DIR, 'valid.csv')
OUTPUT_FILE = os.path.join(BASE_DIR, 'full_multi_source_7days_v6.csv')

# Cấu hình số ngày kéo dữ liệu (Mặc định 15 ngày)
DAYS_BACK = 7
if len(sys.argv) > 1:
    try:
        DAYS_BACK = int(sys.argv[1].replace('--days=', '').strip())
    except ValueError:
        pass

# Network tuning
PAGE_WORKERS     = 10
PAGE_SIZE        = 500      # Dispatch page size
SCAN_PAGE_SIZE   = 1000     # Inbound/Outbound page size
POOL_SIZE        = 64
REQUEST_TIMEOUT  = 60
MAX_RETRIES      = 5
BACKOFF_BASE     = 3
RETRYABLE_STATUS = {405, 429, 500, 502, 503, 504}

LOGIN_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=utf-8',
    'Origin': 'https://jfs.jtcargo.com.vn',
    'Referer': 'https://jfs.jtcargo.com.vn/',
    'lang': 'VN', 'langtype': 'VN',
    'routeName': 'checkToken',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

# ============================================================
# UTILS
# ============================================================
def md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def cfg(filename):
    for d in _cfg_candidates:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    raise FileNotFoundError('Khong tim thay: ' + filename + ' trong bat ky thu muc config nao!')

def clean_wb(val):
    if val is None:
        return ''
    try:
        if pd.isna(val):
            return ''
    except Exception:
        pass
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    if 'e' in s.lower():
        try:
            s = str(int(float(s)))
        except Exception:
            pass
    return s.strip().upper()

def sql_esc(val):
    if val is None or str(val).lower() in ('nan', 'none', 'null', ''):
        return 'NULL'
    return "'" + str(val).replace("'", "''") + "'"

def get_op_date(dt_str: str) -> str:
    """Ngày vận hành theo cycle 06:00–06:00."""
    if not dt_str or str(dt_str).lower() in ('nan', 'none', ''):
        return ''
    try:
        dt = datetime.strptime(str(dt_str)[:19], '%Y-%m-%d %H:%M:%S')
        if dt.hour < 6:
            return (dt.date() - timedelta(days=1)).strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return str(dt_str)[:10]

BACKEND_STATUS_MAP = {
    # Inbound
    'Inbound':              'Inbound',
    'inbound':              'Inbound',
    'at_hub':               'Inbound',
    'Đang trên bãi':        'Inbound',
    'Đã nhập kho':          'Inbound',
    'đã nhập kho':          'Inbound',

    # Transporting
    'Transporting':         'Transporting',
    'transporting':         'Transporting',
    'in_transit':           'Transporting',
    'Đang trên đường':      'Transporting',
    'Đang vận chuyển':      'Transporting',
    'Arrival':              'Transporting',
    'arrival':              'Transporting',
    'Chưa đến HUB':         'Transporting',

    # Pickup Done
    'Pickup Done':          'Pickup Done',
    'pickup_done':          'Pickup Done',
    'picked_up':            'Pickup Done',
    'Đã lấy hàng':          'Pickup Done',
    'đã lấy hàng':          'Pickup Done',

    # Created
    'Created':              'Created',
    'created':              'Created',
    'Dispatched':           'Created',
    'Đã điều phối bưu cục': 'Created',
    'Đã điều phối nhân viên': 'Created',
    'Đã điều phối':         'Created',
    'Lấy hàng thất bại':    'Created',
    'Chưa lấy hàng':        'Created',
    'Lấy lại hàng':         'Created',

    # Outbound
    'Outbound':             'Outbound',
    'outbound':             'Outbound',
    'outbound_done':        'Outbound',
    'Đã xuất kho':          'Outbound',
    'Đã xuất khỏi HUB':     'Outbound',
    'Đã rời HUB':           'Outbound',

    # Canceled
    'Đã hủy':               'Đã hủy',
    'Da huy':               'Đã hủy',
    'da huy':               'Đã hủy',
    'Cancelled':            'Đã hủy',
    'canceled':             'Đã hủy'
}

def clean_status_sys(raw_status: str) -> str:
    """Chuẩn hóa 100% trạng thái thô từ JFS API thành 5 Enum chuẩn dựa trên Data Contract."""
    if not raw_status:
        return 'Created'
    s = str(raw_status).strip()
    if s in BACKEND_STATUS_MAP:
        return BACKEND_STATUS_MAP[s]
    s_lower = s.lower()
    if s_lower in BACKEND_STATUS_MAP:
        return BACKEND_STATUS_MAP[s_lower]
    
    if any(kw in s_lower for kw in ['hủy', 'cancel']):
        return 'Đã hủy'
    if any(kw in s_lower for kw in ['xuất', 'outbound']):
        return 'Outbound'
    if any(kw in s_lower for kw in ['nhập', 'inbound']):
        return 'Inbound'
    if any(kw in s_lower for kw in ['vận chuyển', 'transporting', 'arrival', 'chân', 'chuyến']):
        return 'Transporting'
    if any(kw in s_lower for kw in ['lấy hàng', 'pickup']):
        return 'Pickup Done'
        
    return 'Created'


# ============================================================
# SESSION + TOKEN MANAGER
# ============================================================
def build_session():
    s = requests.Session()
    a = HTTPAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE, max_retries=0)
    s.mount('https://', a)
    s.mount('http://', a)
    return s

class TokenManager:
    def __init__(self, session, account, password, country_id='1', label=''):
        self.session    = session
        self.account    = account
        self.password   = password
        self.country_id = country_id
        self.label      = label or account
        self._token     = None
        self._lock      = threading.Lock()

    def _login(self):
        payload = {'account': self.account, 'password': md5(self.password),
                   'captchaToken': '', 'countryId': self.country_id}
        for attempt in range(1, 4):
            try:
                r = self.session.post(LOGIN_URL, headers=LOGIN_HEADERS,
                                      json=payload, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                res = r.json()
                if res.get('code') == 1 or res.get('succ'):
                    data = res.get('data', {})
                    token = (data.get('token') or data.get('authToken')
                             or (data if isinstance(data, str) else None))
                    if token:
                        return token
                print('   [' + self.label + '] Login that bai: ' + str(res.get('msg', '')))
            except Exception as e:
                print('   [' + self.label + '] Loi mang login lan ' + str(attempt) + ': ' + str(e))
            time.sleep(2 * attempt)
        raise RuntimeError('[' + self.label + '] Dang nhap that bai sau 3 lan.')

    def get_token(self):
        with self._lock:
            if self._token is None:
                self._token = self._login()
                print('   OK [' + self.label + '] token: ' + self._token[:12] + '...')
            return self._token

    def refresh(self, stale):
        with self._lock:
            if self._token is None or self._token == stale:
                print('   401/405 [' + self.label + '] -> login lai...')
                self._token = self._login()
            return self._token

# ============================================================
# AUTH POST
# ============================================================
def auth_post(session, url, token_mgr, base_headers,
              params=None, json_body=None, data=None, label=''):
    last_exc  = None
    refreshed = False
    attempt   = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        token   = token_mgr.get_token()
        hdrs    = dict(base_headers)
        hdrs['authToken'] = token
        hdrs['Authtoken'] = token
        try:
            r = session.post(url, params=params, headers=hdrs,
                             json=json_body, data=data, timeout=REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            time.sleep(BACKOFF_BASE * attempt)
            continue
        if (r.status_code == 401 or r.status_code == 405) and not refreshed:
            token_mgr.refresh(token)
            refreshed = True
            attempt  -= 1
            continue
        if r.status_code in RETRYABLE_STATUS:
            last_exc = requests.exceptions.HTTPError(str(r.status_code) + ' ' + url)
            time.sleep(BACKOFF_BASE * attempt)
            continue
        r.raise_for_status()
        return r
    raise last_exc if last_exc else RuntimeError(label + ': that bai sau ' + str(MAX_RETRIES) + ' lan')

# ============================================================
# PAGE PULLERS
# ============================================================
def pull_pages_parallel(fetch_fn, total, page_size, label, start_page=1):
    n_pages = math.ceil(total / page_size)
    pages   = list(range(start_page, n_pages + 1))
    print('   ' + label + ': ' + str(len(pages)) + ' trang song song...')
    results, failed = {}, []
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        fmap = {ex.submit(fetch_fn, p): p for p in pages}
        for f in as_completed(fmap):
            p = fmap[f]
            try:
                results[p] = f.result()
            except Exception as e:
                print('   ' + label + ' trang ' + str(p) + ': ' + str(e))
                failed.append(p)
    for p in failed:
        for att in range(1, MAX_RETRIES + 1):
            time.sleep(BACKOFF_BASE * att)
            try:
                results[p] = fetch_fn(p)
                break
            except Exception:
                pass
        else:
            results[p] = []
    out = []
    for p in pages:
        out.extend(results.get(p, []))
    return out

def pull_pages_seq(fetch_fn, page_size, label, start_page=1):
    all_data, page = [], start_page
    while True:
        try:
            rows = fetch_fn(page)
        except Exception as e:
            print('   ' + label + ' trang ' + str(page) + ': ' + str(e))
            break
        if not rows:
            break
        all_data.extend(rows)
        if len(rows) < page_size:
            break
        page += 1
    return all_data

# ============================================================
# SOURCE 1: DISPATCH
# ============================================================
def pull_dispatch(session, token_mgr, headers, base_payload, label='Dispatch'):
    page_size = int(base_payload.get('size', PAGE_SIZE))

    def fetch_page(p):
        pl = dict(base_payload)
        pl['current'] = str(p)
        r = auth_post(session, URL_DISPATCH, token_mgr,
                      headers, data=pl, label=label + ' p' + str(p))
        obj = r.json().get('data', {})
        recs = obj.get('records') or obj.get('list') or obj.get('rows') or []
        return recs, obj

    try:
        recs1, obj1 = fetch_page(1)
    except Exception as e:
        print('   ' + label + ' trang 1 loi: ' + str(e))
        return []

    total    = obj1.get('total', None)
    total    = total if isinstance(total, int) else None
    all_data = list(recs1)
    print('   ' + label + ' total: ' + (str(total) if total else '?'))

    if recs1:
        if total is not None and total > len(recs1):
            rest = pull_pages_parallel(lambda p: fetch_page(p)[0],
                                       total, page_size, label, start_page=2)
            all_data.extend(rest)
        elif total is None:
            seq = pull_pages_seq(lambda p: fetch_page(p)[0],
                                 page_size, label, start_page=2)
            all_data.extend(seq)

    print('   OK ' + label + ': ' + str(len(all_data)) + ' dong')
    return all_data

# ============================================================
# SOURCE 2 & 3: INBOUND / OUTBOUND
# ============================================================
def pull_scan(session, token_mgr, headers, params, base_payload, label=''):
    page_size = int(base_payload.get('size', SCAN_PAGE_SIZE))
    total = None
    try:
        count_pl = dict(base_payload)
        count_pl.update({'paginationSearchType': 'count', 'size': 1, 'current': 1})
        r = auth_post(session, URL_SCAN, token_mgr, headers,
                      params=params, json_body=count_pl, label=label + ' count')
        t = r.json().get('data', {})
        if isinstance(t, str):
            try: t = json.loads(t)
            except: t = {}
        total = t.get('total', None) if isinstance(t, dict) else None
        total = total if isinstance(total, int) else None
    except Exception as e:
        print('   ' + label + ' count loi: ' + str(e))

    print('   ' + label + ' total: ' + (str(total) if total else '?'))

    def fetch_page(p):
        pl = dict(base_payload)
        pl.update({'paginationSearchType': 'list', 'current': p})
        r  = auth_post(session, URL_SCAN, token_mgr, headers,
                       params=params, json_body=pl, label=label + ' p' + str(p))
        dn = r.json().get('data') or {}
        if isinstance(dn, str):
            try: dn = json.loads(dn)
            except: dn = {}
        return dn.get('records', []) or []

    if total and total > 0:
        all_data = pull_pages_parallel(fetch_page, total, page_size, label)
    else:
        all_data = pull_pages_seq(fetch_page, page_size, label)

    print('   OK ' + label + ': ' + str(len(all_data)) + ' dong')
    return all_data

# ============================================================
# SOURCE 4: LINEHAUL OPS
# ============================================================
def pull_linehaul_ops(session, token_mgr, start_str, end_str):
    label = 'Linehaul Ops'
    hdrs  = {'Accept': 'application/json, text/plain, */*',
             'Content-Type': 'application/json;charset=utf-8',
             'lang': 'VN', 'langtype': 'VN',
             'routeName': 'opsTraceSub', 'User-Agent': 'Mozilla/5.0'}
    base_pl = {'countryId': '1', 'current': 1, 'size': 1000,
               'searchType': 1, 'startScanTime': start_str, 'endScanTime': end_str,
               'traceCodes': [], 'traceSubCodes': []}
    try:
        r   = auth_post(session, URL_LINEHAUL_OPS, token_mgr, hdrs,
                        json_body=base_pl, label=label)
        raw = r.json().get('data')
        obj = json.loads(raw) if isinstance(raw, str) else raw
        tot = obj.get('total', 0) if isinstance(obj, dict) else 0
        print('   ' + label + ' total: ' + str(tot))
        if not tot:
            return []
        n_pg = math.ceil(tot / 1000)
        res  = {}
        def fetch_p(p):
            pl = dict(base_pl); pl['current'] = p
            rp = auth_post(session, URL_LINEHAUL_OPS, token_mgr, hdrs,
                           json_body=pl, label=label + ' p' + str(p))
            rw = rp.json().get('data')
            ob = json.loads(rw) if isinstance(rw, str) else rw
            return ob.get('records', []) if isinstance(ob, dict) else []
        with ThreadPoolExecutor(max_workers=5) as ex:
            fm = {ex.submit(fetch_p, p): p for p in range(1, n_pg + 1)}
            for f in as_completed(fm): res[fm[f]] = f.result()
        out = []
        for p in range(1, n_pg + 1): out.extend(res.get(p, []))
        print('   OK ' + label + ': ' + str(len(out)))
        return out
    except Exception as e:
        print('   ' + label + ' loi: ' + str(e))
        return []

# ============================================================
# SOURCE 5: LINEHAUL CONSOLIDATED
# ============================================================
def pull_linehaul_consol(session, token_mgr, start_str, end_str):
    label  = 'Linehaul Consol'
    hdrs   = {'Accept': 'application/json, text/plain, */*',
              'Content-Type': 'application/json;charset=utf-8',
              'lang': 'VN', 'langtype': 'VN',
              'routeName': 'scanQueryConstantlyNew|businessIndicatorIndex',
              'User-Agent': 'Mozilla/5.0'}
    base_pl = {'countryId': '1', 'current': 1, 'size': 1000,
               'startTime': start_str, 'endTime': end_str,
               'sqlCode': 'transport_consolidated_report', 'timeType': '2'}
    params = {'sqlCode': 'transport_consolidated_report',
              'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693'}
    try:
        cnt_pl = dict(base_pl); cnt_pl['paginationSearchType'] = 'count'
        r   = auth_post(session, URL_SCAN, token_mgr, hdrs,
                        params=params, json_body=cnt_pl, label=label)
        raw = r.json().get('data')
        obj = json.loads(raw) if isinstance(raw, str) else raw
        tot = obj.get('total', 0) if isinstance(obj, dict) else 0
        print('   ' + label + ' total: ' + str(tot))
        if not tot:
            return []
        n_pg = math.ceil(tot / 1000)
        res  = {}
        def fetch_p(p):
            pl = dict(base_pl); pl.update({'paginationSearchType': 'list', 'current': p})
            rp = auth_post(session, URL_SCAN, token_mgr, hdrs,
                           params=params, json_body=pl, label=label + ' p' + str(p))
            rw = rp.json().get('data')
            ob = json.loads(rw) if isinstance(rw, str) else rw
            return ob.get('records', []) if isinstance(ob, dict) else []
        with ThreadPoolExecutor(max_workers=5) as ex:
            fm = {ex.submit(fetch_p, p): p for p in range(1, n_pg + 1)}
            for f in as_completed(fm): res[fm[f]] = f.result()
        out = []
        for p in range(1, n_pg + 1): out.extend(res.get(p, []))
        print('   OK ' + label + ': ' + str(len(out)))
        return out
    except Exception as e:
        print('   ' + label + ' loi: ' + str(e))
        return []

# ============================================================
# SOURCE 6: ARRIVAL
# ============================================================
def pull_arrival(session, arr_tmgr, ib_headers, start_str, end_str):
    label = 'Arrival'
    try:
        master_path = cfg('stations_master.csv')
    except Exception:
        master_path = ''

    station_names = []
    if master_path and os.path.exists(master_path):
        try:
            df_m = pd.read_csv(master_path)
            df_f = df_m[
                df_m['master_area'].astype(str).str.contains('HCM|SE|HN', na=False, case=False) |
                df_m['station_name'].astype(str).str.contains('BN HUB', na=False, case=False)
            ]
            station_names = df_f['station_name'].dropna().unique().tolist()
        except Exception:
            pass

    d_sc = {}
    try:
        vp = cfg('valid.csv')
    except Exception:
        vp = ''

    if vp and os.path.exists(vp):
        try:
            df_v = pd.read_csv(vp, dtype=str)
            df_v.columns = df_v.columns.str.strip()
            nc = next((c for c in ['Station_1', 'Station_2', 'Buu cuc', 'Bưu cục', 'Buu cuc final', 'Bưu cục final']
                       if c in df_v.columns), None)
            if nc and 'sortcode' in df_v.columns:
                for _, row in df_v[[nc, 'sortcode']].dropna().iterrows():
                    k = str(row[nc]).strip().upper()
                    v = str(row['sortcode']).strip()
                    if v and 'nan' not in v.lower() and 'offline' not in v.lower():
                        d_sc[k] = v
        except Exception:
            pass

    stations = []
    for name in station_names:
        key  = str(name).strip().upper()
        code = d_sc.get(key)
        if not code:
            for k, v in d_sc.items():
                if key in k or k in key:
                    code = v; break
        if code:
            stations.append({'name': name.strip(), 'code': code})

    # Strictly pull Arrival only for stations listed in stations_master.csv
    print('   ' + label + ': ' + str(len(stations)) + ' buu cuc (stritcly filtered by stations_master.csv)...')
    arr_params = {'sqlCode': 'realtime_sca_sen_mon_dtl',
                  'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693'}
    all_recs = []
    lock     = threading.Lock()

    def fetch_one(st):
        pl = {'beginDate': start_str, 'endDate': end_str,
              'countryId': '1', 'size': 1000,
              'sqlCode': 'realtime_sca_sen_mon_dtl',
              'scanSiteCode': st['code'], 'scanSiteCodeId': '',
              'scanSiteCodeName': st['name'], 'scanSiteCodeTypeId': ''}
        recs = []
        page = 1
        while True:
            try:
                lpl = dict(pl); lpl.update({'paginationSearchType': 'list', 'current': page})
                r   = auth_post(session, URL_SCAN, arr_tmgr, ib_headers,
                                params=arr_params, json_body=lpl,
                                label=label + '/' + st['name'])
                dn  = r.json().get('data')
                if isinstance(dn, str):
                    try: dn = json.loads(dn)
                    except: dn = {}
                rows = dn.get('records', []) if isinstance(dn, dict) else (dn or [])
                if not rows: break
                recs.extend(rows)
                if len(rows) < 1000: break
                page += 1
            except Exception: break
        if recs:
            with lock: all_recs.extend(recs)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(fetch_one, stations))
    print('   OK ' + label + ': ' + str(len(all_recs)))
    return all_recs

# ============================================================
# SOURCE 7: SHUTTLE TRACKING
# ============================================================
def pull_shuttle(session, arr_tmgr, start_str, end_str):
    label   = 'Shuttle Tracking'
    hdrs    = {'Accept': 'application/json, text/plain, */*',
               'Content-Type': 'application/json;charset=utf-8',
               'lang': 'VN', 'langtype': 'VN',
               'routeName': 'brancTaskTrackSearch', 'User-Agent': 'Mozilla/5.0'}
    base_pl = {'countryId': '1', 'current': 1, 'size': 1000,
               'startDepartureTime': start_str, 'endDepartureTime': end_str}
    try:
        r   = auth_post(session, URL_SHUTTLE_TRACK, arr_tmgr, hdrs,
                        json_body=base_pl, label=label)
        raw = r.json().get('data')
        obj = json.loads(raw) if isinstance(raw, str) else raw
        tot = obj.get('total', 0) if isinstance(obj, dict) else 0
        print('   ' + label + ' total: ' + str(tot))
        if not tot: return []
        n_pg = math.ceil(tot / 1000)
        res  = {}
        def fetch_p(p):
            pl = dict(base_pl); pl['current'] = p
            rp = auth_post(session, URL_SHUTTLE_TRACK, arr_tmgr, hdrs,
                           json_body=pl, label=label + ' p' + str(p))
            rw = rp.json().get('data')
            ob = json.loads(rw) if isinstance(rw, str) else rw
            return ob.get('records', []) if isinstance(ob, dict) else []
        with ThreadPoolExecutor(max_workers=5) as ex:
            fm = {ex.submit(fetch_p, p): p for p in range(1, n_pg + 1)}
            for f in as_completed(fm): res[fm[f]] = f.result()
        out = []
        for p in range(1, n_pg + 1): out.extend(res.get(p, []))
        print('   OK ' + label + ': ' + str(len(out)))
        return out
    except Exception as e:
        print('   ' + label + ' loi: ' + str(e))
        return []

# ============================================================
# PULL BACKLOG REPORT (realtime_inv_man_dtl)
# ============================================================
def pull_backlog(session, token_mgr, bh_headers, bp_payload, start_str, end_str):
    url = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
    params = {
        'sqlCode': bp_payload.get('sqlCode', 'realtime_inv_man_dtl'),
        'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
        'routeName': bh_headers.get('routeName', ''),
    }
    hdrs = bh_headers.copy()

    pl = bp_payload.copy()
    pl['beginDate'] = start_str
    pl['endDate']   = end_str
    pl['size']      = SCAN_PAGE_SIZE

    print('   Backlog (Hàng Tồn Realtime)...', flush=True)
    count_payload = pl.copy()
    count_payload['paginationSearchType'] = 'count'
    count_payload['size'] = 1

    total = 0
    try:
        r = auth_post(session, url, token_mgr, hdrs, params=params, json_body=count_payload, label='Backlog count')
        total = r.json().get('data', {}).get('total', 0) or 0
    except Exception as e:
        print('   Backlog count error: ' + str(e))

    if total <= 0:
        print('   OK Backlog: 0 dong')
        return []

    def fetch_backlog_page(p):
        page_payload = pl.copy()
        page_payload['current'] = p
        page_payload['paginationSearchType'] = 'list'
        try:
            r = auth_post(session, url, token_mgr, hdrs, params=params, json_body=page_payload, label='Backlog p' + str(p))
            return r.json().get('data', {}).get('records', []) or []
        except Exception:
            return []


    records = pull_pages_parallel(fetch_backlog_page, total, SCAN_PAGE_SIZE, 'Backlog Report JFS')
    print('   OK Backlog: ' + str(len(records)) + ' dong')
    return records



# ============================================================
# OPTIMIZED BATCH FORECAST PULLER (100 mã / batch)
# ============================================================
def pull_forecast_by_bills(session, token_mgr, base_payload, bills_list):
    bills_list = list(set([clean_wb(b) for b in bills_list if b]))
    if not bills_list:
        return []
    batch_size = 100
    batches = [bills_list[i:i + batch_size] for i in range(0, len(bills_list), batch_size)]
    print('   Forecast Batch: Tra cuu ' + str(len(bills_list)) + ' don hang trong ' + str(len(batches)) + ' lo...')
    
    all_records = []
    lock = threading.Lock()
    unauthorized = threading.Event()
    hdrs = {'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'lang': 'VN', 'langtype': 'VN',
            'routeName': 'shippingWaybillList', 'User-Agent': 'Mozilla/5.0'}

    def fetch_batch(batch):
        if unauthorized.is_set():
            return
        pl = dict(base_payload)
        pl.update({'waybillNos': ','.join(batch), 'size': batch_size, 'current': 1,
                   'timeStart': '', 'timeEnd': '', 'inputTimeStart': '', 'inputTimeEnd': ''})
        try:
            r = auth_post(session, URL_FORECAST, token_mgr, hdrs, data=pl, label='Forecast batch')
            data = r.json().get('data', []) or []
            if isinstance(data, dict):
                data = data.get('records', []) or []
            with lock:
                all_records.extend(data)
        except Exception as e:
            if '401' in str(e) or '403' in str(e):
                if not unauthorized.is_set():
                    print('   ⚠️  Forecast API không có quyền truy cập (401 Unauthorized) — bỏ qua tra cứu Forecast batch.')
                    unauthorized.set()
            else:
                pass

    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        ex.map(fetch_batch, batches)

    print('   OK Forecast Batch: ' + str(len(all_records)) + ' dong')
    return all_records

# ============================================================
# SO KHỚP CHRONOLOGICAL (IN ↔ OUT)
# ============================================================
def merge_in_out_chronological(df_in: pd.DataFrame, df_out: pd.DataFrame) -> pd.DataFrame:
    if df_in.empty and df_out.empty:
        return pd.DataFrame()
    if df_in.empty:
        return df_out
    if df_out.empty:
        return df_in

    df_in_sorted  = df_in.sort_values(['billNo', 'scanDate']).copy()
    df_out_sorted = df_out.sort_values(['billNo', 'scanDate']).copy()

    df_in_sorted['billNo']  = df_in_sorted['billNo'].apply(clean_wb)
    df_out_sorted['billNo'] = df_out_sorted['billNo'].apply(clean_wb)

    in_dict = {}
    for idx, bill, s_date in df_in_sorted[['billNo', 'scanDate']].itertuples(name=None):
        in_dict.setdefault(bill, []).append((idx, s_date))

    out_dict = {}
    for idx, bill, s_date in df_out_sorted[['billNo', 'scanDate']].itertuples(name=None):
        out_dict.setdefault(bill, []).append((idx, s_date))

    matched_pairs, unmatched_in, unmatched_out = [], [], []
    all_bills = set(in_dict.keys()).union(out_dict.keys())
    TOLERANCE = pd.Timedelta(minutes=10)

    for bill in sorted(all_bills):
        in_list  = in_dict.get(bill, [])
        out_list = out_dict.get(bill, [])

        if not in_list:
            unmatched_out.extend([x[0] for x in out_list])
            continue
        if not out_list:
            unmatched_in.extend([x[0] for x in in_list])
            continue

        i, j = 0, 0
        n_in, n_out = len(in_list), len(out_list)

        while i < n_in and j < n_out:
            in_idx, in_time   = in_list[i]
            out_idx, out_time = out_list[j]

            if out_time >= in_time - TOLERANCE:
                if i + 1 < n_in and in_list[i+1][1] - TOLERANCE < out_time:
                    unmatched_in.append(in_idx)
                    i += 1
                else:
                    matched_pairs.append((in_idx, out_idx))
                    i += 1; j += 1
            else:
                unmatched_out.append(out_idx)
                j += 1

        while i < n_in:
            unmatched_in.append(in_list[i][0]); i += 1
        while j < n_out:
            unmatched_out.append(out_list[j][0]); j += 1

    matched_in_idxs  = [p[0] for p in matched_pairs]
    matched_out_idxs = [p[1] for p in matched_pairs]

    df_matched_in  = df_in_sorted.loc[matched_in_idxs].reset_index(drop=True)
    df_matched_out = df_out_sorted.loc[matched_out_idxs].reset_index(drop=True)

    rename_map = {c: f"{c}_out" for c in df_out.columns if c != 'billNo'}
    df_matched_out_r = df_matched_out.rename(columns=rename_map)

    df_matched  = pd.concat([df_matched_in, df_matched_out_r.drop(columns=['billNo'])], axis=1)
    df_only_in  = df_in_sorted.loc[unmatched_in].reset_index(drop=True)
    df_only_out = df_out_sorted.loc[unmatched_out].reset_index(drop=True).rename(columns=rename_map)

    return pd.concat([df_matched, df_only_in, df_only_out], ignore_index=True).reset_index(drop=True)

# ============================================================
# MAIN
# ============================================================
def main():
    tz_vn  = ZoneInfo('Asia/Ho_Chi_Minh')
    now    = datetime.now(tz_vn)
    start_dt = now - timedelta(days=DAYS_BACK)

    start_str     = start_dt.strftime('%Y-%m-%d 00:00:00')
    end_str       = now.strftime('%Y-%m-%d %H:%M:%S')
    end_str_plus1 = (now + timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')

    print('=' * 65)
    print(f'PIPELINE UNIFIED V6 -- Song song 7 nguon ({DAYS_BACK} ngay), khong file trung gian')
    print(start_str + '  ->  ' + end_str)
    print('=' * 65)

    session_main = build_session()
    session_arr  = build_session()
    tkn_main = TokenManager(session_main, ACCOUNT,     PASSWORD,     label='660021')
    tkn_arr  = TokenManager(session_arr,  ARR_ACCOUNT, ARR_PASSWORD, label='660085')

    print('\nLogin song song 2 tai khoan...')
    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(tkn_main.get_token)
        fb = ex.submit(tkn_arr.get_token)
        fa.result(); fb.result()

    ih_headers = load_json(cfg('inboundheaders.json'))
    ip_payload = load_json(cfg('inboundpayload.json'))
    oh_headers = load_json(cfg('outboundheaders.json'))
    op_payload = load_json(cfg('outboundpayload.json'))

    ip_payload['beginDate'] = start_str;  ip_payload['endDate'] = end_str
    op_payload['beginDate'] = start_str;  op_payload['endDate'] = end_str

    i_params = {'sqlCode': ip_payload.get('sqlCode', ''),
                'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
                'routeName': ih_headers.get('routeName', '')}
    o_params = {'sqlCode': op_payload.get('sqlCode', ''),
                'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
                'routeName': oh_headers.get('routeName', '')}

    dh_headers = load_json(cfg('dispatchheaders.json'))
    dp_payload = load_json(cfg('dispatchpayload.json'))
    dp_payload['startInputTime'] = start_str
    dp_payload['endInputTime']   = end_str
    dp_payload['current']        = '1'
    dp_payload['size']           = str(PAGE_SIZE)

    bh_headers = load_json(cfg('backlogheaders.json'))
    bp_payload = load_json(cfg('backlogpayload.json'))
    bp_payload['beginDate'] = start_str

    # ── Phase 1: Keo song song 8 nguon ──────────────────────
    print('\nPhase 1 -- Keo song song 8 nguon...')
    t0  = time.time()
    raw = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(pull_dispatch,       session_main, tkn_main, dh_headers, dp_payload):        'dispatch',
            ex.submit(pull_scan,           session_main, tkn_main, ih_headers, i_params, ip_payload, 'Inbound'):  'inbound',
            ex.submit(pull_scan,           session_main, tkn_main, oh_headers, o_params, op_payload, 'Outbound'): 'outbound',
            ex.submit(pull_linehaul_ops,   session_main, tkn_main, start_str, end_str):              'lh_ops',
            ex.submit(pull_linehaul_consol,session_main, tkn_main, start_str, end_str_plus1):        'lh_consol',
            ex.submit(pull_arrival,        session_arr,  tkn_arr,  ih_headers, start_str, end_str):  'arrival',
            ex.submit(pull_shuttle,        session_arr,  tkn_arr,  start_str, end_str):              'shuttle',
            ex.submit(pull_backlog,        session_main, tkn_main, bh_headers, bp_payload, start_str, end_str): 'backlog',

        }

        for f in as_completed(futures):
            key = futures[f]
            try:
                raw[key] = f.result()
            except Exception as e:
                print('   FAIL ' + key + ': ' + str(e))
                raw[key] = []

    print('\nPhase 1 xong: ' + str(round(time.time() - t0, 1)) + 's')
    for k, v in raw.items():
        print('   ' + k.ljust(20) + ': ' + str(len(v)) + ' ban ghi')

    # ── Phase 2: trip_time_map ───────────────────────────────
    print('\nPhase 2 -- trip_time_map...')
    ttm = {}

    for t in raw.get('shuttle', []):
        c = clean_wb(t.get('shipmentNo') or t.get('taskNo'))
        s = str(t.get('actualDepartureTime') or t.get('appDepartureTime') or t.get('loadStartTime') or '').strip()
        a = str(t.get('actualArrivalTime') or t.get('unloadStartTime') or t.get('appArrivalTime') or '').strip()
        if c: ttm[c] = {'transporing_time': s, 'transported_time': a}

    for t in raw.get('lh_ops', []):
        for c in [clean_wb(t.get('traceCode')), clean_wb(t.get('traceSubCode'))]:
            if not c: continue
            s = str(t.get('sendTime') or t.get('loadingEndTime') or t.get('loadingStartTime') or '').strip()
            a = str(t.get('unloadingStartTime') or t.get('unloadingEndTime') or t.get('arriveTime') or '').strip()
            if c not in ttm:
                ttm[c] = {'transporing_time': s, 'transported_time': a}
            else:
                if not ttm[c]['transporing_time'] and s: ttm[c]['transporing_time'] = s
                if not ttm[c]['transported_time'] and a: ttm[c]['transported_time'] = a

    for t in raw.get('lh_consol', []):
        c = clean_wb(t.get('shipmentNo') or t.get('shipmentNos'))
        s = str(t.get('actualDepartureTime') or t.get('trackOutTime') or t.get('scanTime') or '').strip()
        a = str(t.get('actualArrivalTime') or t.get('unLoadingScanStartTime') or t.get('trackInTime') or '').strip()
        if c and c not in ttm: ttm[c] = {'transporing_time': s, 'transported_time': a}

    print('   trip_time_map: ' + str(len(ttm)) + ' chuyen xe')

    # ── Phase 3: Xu ly Dispatch ──────────────────────────────
    print('\nPhase 3 -- Xu ly Dispatch...')

    vp  = find_config_file('valid.csv') or (VALID_FILE if os.path.exists(VALID_FILE) else os.path.join(CONFIG_DIR, 'valid.csv'))
    print(f'   📌 Read valid.csv from: {vp} (Exists: {os.path.exists(vp)})')
    valid_codes  = set()
    dict_station = {}
    dict_area    = {}

    dict_round   = {}
    dict_rank    = {}

    if os.path.exists(vp):
        try:
            dfv = pd.read_csv(vp, dtype=str)
            dfv.columns = dfv.columns.str.strip()
            st2_col  = next((c for c in ['Station_2', 'Station_1', 'Bưu cục'] if c in dfv.columns), '')
            sc_col   = next((c for c in ['sortcode', 'Dispatch_code'] if c in dfv.columns), '')
            hub_col  = next((c for c in ['Hubcode', 'Hub_code'] if c in dfv.columns), '')
            area_col = next((c for c in ['area', 'AreaID'] if c in dfv.columns), '')


            for _, r_v in dfv.iterrows():
                st2 = str(r_v.get(st2_col) or '').strip()
                st1 = str(r_v.get('Station_1') or '').strip().upper()
                ar  = str(r_v.get(area_col) or '').strip()
                rn  = str(r_v.get('Round') or '').strip()
                rk  = str(r_v.get('Rank') or '').strip()

                if st1:
                    dict_station[st1] = st2
                    dict_area[st1]    = ar
                    dict_round[st1]   = rn
                    dict_rank[st1]    = rk

                if sc_col and r_v.get(sc_col):
                    sc = str(r_v.get(sc_col)).strip().upper()
                    if sc:
                        dict_station[sc] = st2
                        dict_area[sc]    = ar
                        dict_round[sc]   = rn
                        dict_rank[sc]    = rk
                        valid_codes.add(sc)
                        if len(sc) >= 6:
                            dict_station[sc[:6]] = st2
                            dict_area[sc[:6]]    = ar
                            dict_round[sc[:6]]   = rn
                            dict_rank[sc[:6]]    = rk
                            valid_codes.add(sc[:6])

                if hub_col and r_v.get(hub_col):
                    hub = str(r_v.get(hub_col)).strip().upper()
                    if hub and hub not in ('SR0001', 'SR0002'):
                        dict_station[hub] = st2
                        dict_area[hub]    = ar
                        dict_round[hub]   = rn
                        dict_rank[hub]    = rk
                        valid_codes.add(hub)
                        if len(hub) >= 6:
                            dict_station[hub[:6]] = st2
                            dict_area[hub[:6]]    = ar
                            dict_round[hub[:6]]   = rn
                            dict_rank[hub[:6]]    = rk
                            valid_codes.add(hub[:6])


        except Exception as e:
            print('   Loi doc valid.csv: ' + str(e))

    def extract_ma10(val):
        if not val or str(val).strip() == '': return ''
        ms = re.findall(r'[A-Z]{2,3}\d{3}[A-Z0-9]', str(val))
        for m in ms:
            if m in valid_codes: return m
        return ms[0] if ms else ''

    seen_wb  = set()
    rows_v6  = []
    raw_vals = []
    batch_id = 'B-V6-' + now.strftime('%Y%m%d%H%M')

    for rec in raw.get('dispatch', []):
        wb  = clean_wb(rec.get('waybillId') or rec.get('waybillNo'))
        ct  = str(rec.get('inputTime') or rec.get('dispatchNetworkTime') or '').strip()
        dr  = str(rec.get('terminalDispatchCode') or '').strip().upper()
        if not wb or not ct or wb in seen_wb: continue
        seen_wb.add(wb)
        if str(rec.get('orderStatusName') or '').strip() == 'Da huy': continue

        dc   = extract_ma10(dr) or dr
        stn  = clean_status_sys(str(rec.get('orderStatusName') or '').strip())
        pkn  = str(rec.get('pickNetworkName') or '').strip()
        num  = int(rec.get('packageNumber') or 1)
        wt   = float(rec.get('packageChargeWeight') or 0.0)
        pt   = str(rec.get('pickTime') or '').strip()
        opd  = ct[:10]
        nxst = dict_station.get(dc, '')

        rows_v6.append({
            'tracking': wb, 'status_sys': stn, 'Created_time': ct,
            'Pickup_station': pkn, 'Dispatch_code': dc,
            'Orders_num': num, 'Orders_weight': wt,
            'Pickup_station2': str(rec.get('realPickNetworkName') or ''),
            'Pickup_time': pt, 'AreaCode': str(rec.get('proxyAreaCode') or ''),
            'flowTypeDesc': str(rec.get('flowTypeDesc') or ''),
            'Next_station': nxst, 'Round': dict_round.get(dc, ''),
            'Rank': dict_rank.get(dc, ''),
            'inbound_scanDate': '', 'outbound_scanDate': '',
            'arrival_scanDate': '', 'trip_code': '',
            'transporing_time': '', 'transported_time': '',
        })
        raw_vals.append(
            '(' + sql_esc(wb) + ',' + sql_esc(ct) + ',' + sql_esc(stn) + ',' +
            sql_esc(pkn) + ',' + sql_esc(dc) + ',' + str(num) + ',' + str(wt) + ',' +
            sql_esc(pt) + ',' + sql_esc(batch_id) + ',' + sql_esc(opd) + ',' + sql_esc(wb) + ')'
        )

    print('   Dispatch sau dedup: ' + str(len(rows_v6)) + ' don hop le')

    # ── Phase 4: Lookup maps ─────────────────────────────────
    print('\nPhase 4 -- Lookup maps...')
    ib_scan_map, ib_trip_map, ib_station_map = {}, {}, {}
    for r in raw.get('inbound', []):
        wb = clean_wb(r.get('billNo') or r.get('waybillNo'))
        st = str(r.get('scanDate') or '').strip()
        tc = clean_wb(r.get('transferCode') or r.get('transfercode') or r.get('billTaskCode'))
        # Lấy "Trạm trước / Trạm tiếp theo" (upOrNextStation / sendSite) từ JFS Inbound API
        send_st = str(r.get('upOrNextStation') or r.get('sendSite') or r.get('sendNetworkName') or '').strip()

        if wb and st and st.lower() not in ('nan', 'none', ''):
            if wb not in ib_scan_map or st > ib_scan_map[wb]:
                ib_scan_map[wb] = st
                if tc: ib_trip_map[wb] = tc
                if send_st: ib_station_map[wb] = send_st

        # Bổ sung các vận đơn Inbound liên miền / Miền Bắc không nằm trong Dispatch local
        if wb and wb not in seen_wb:
            seen_wb.add(wb)
            wt = float(r.get('weight') or r.get('settlementWeight') or 0.0)
            rows_v6.append({
                'tracking': wb, 'status_sys': 'Inbound', 'Created_time': st,
                'Pickup_station': send_st, 'Dispatch_code': '',
                'Orders_num': int(r.get('piece') or 1),
                'Orders_weight': (wt / 1000.0) if wt > 5000.0 else (wt if wt > 0 else 1.5),
                'Pickup_station2': send_st,
                'Pickup_time': '', 'AreaCode': '',
                'flowTypeDesc': 'Inbound Linehaul',
                'Next_station': '', 'Round': '', 'Rank': '',

                'inbound_scanDate': st, 'outbound_scanDate': '',
                'arrival_scanDate': '', 'trip_code': tc,
                'transporing_time': '', 'transported_time': '',
            })

    ob_map, ob_next_station_map, ob_trip_map = {}, {}, {}
    for r in raw.get('outbound', []):
        wb = clean_wb(r.get('billNo') or r.get('waybillNo'))
        st = str(r.get('scanDate') or r.get('scanTime') or r.get('inputDate') or '').strip()
        next_st = str(r.get('upOrNextStation') or r.get('nextSite') or r.get('nextSiteName') or r.get('nextNetworkName') or r.get('next_network') or r.get('receiveSite') or r.get('receiveSiteName') or '').strip()
        trip = clean_wb(r.get('transferCode') or r.get('transfercode') or r.get('billTaskCode') or r.get('taskCode'))
        if wb:
            if not st: st = '2026-07-30 00:00:00'
            if wb not in ob_map or st >= ob_map[wb]:
                ob_map[wb] = st
                if next_st:
                    ob_next_station_map[wb] = next_st
                if trip:
                    ob_trip_map[wb] = trip

    arr_scan_map, arr_trip_map, arr_station_map = {}, {}, {}
    for r in raw.get('arrival', []):
        wb   = clean_wb(r.get('billcode') or r.get('waybillNo') or r.get('billNo'))
        st   = str(r.get('scantime') or r.get('scanDate') or '').strip()
        send_st = str(r.get('last_dept_name') or r.get('scansitename') or r.get('sendSite') or r.get('sendNetworkName') or r.get('upOrNextStation') or '').strip()
        trip = clean_wb(r.get('transfercode') or r.get('transferCode') or
                        r.get('traceCode') or r.get('traceSubCode') or
                        r.get('billTaskCode') or r.get('taskCode'))
        if wb:
            if wb not in arr_scan_map or (st and st > arr_scan_map[wb]):
                arr_scan_map[wb] = st
                if trip: arr_trip_map[wb] = trip
                if send_st: arr_station_map[wb] = send_st

    backlog_info_map = {}
    for r in raw.get('backlog', []):
        wb = clean_wb(r.get('billcode') or r.get('billNo') or r.get('waybillNo'))
        dest_st = str(r.get('destination_site_name') or r.get('SEND_NEXTSTATION') or r.get('destinationSiteName') or '').strip()
        abnormal_rmk = str(r.get('abnormal_remark') or r.get('ABNORMAL_REMARK') or r.get('abnormal_reason') or r.get('abnormalRemark') or '').strip()
        take_st = str(r.get('take_site_name') or r.get('TAKE_SITE_NAME') or r.get('takeSiteName') or r.get('take_site') or '').strip()
        if wb:
            backlog_info_map[wb] = {
                'dest': dest_st,
                'remark': abnormal_rmk,
                'take_site': take_st
            }

    print('   Inbound  map: ' + str(len(ib_scan_map)) + ' don (bao gồm ' + str(len(ib_station_map)) + ' trạm nguồn upOrNextStation/sendSite)')
    print('   Outbound map: ' + str(len(ob_map)) + ' don (bao gồm ' + str(len(ob_next_station_map)) + ' trạm đích nextSite)')
    print('   Arrival  map: ' + str(len(arr_scan_map)) + ' don (bao gồm ' + str(len(arr_station_map)) + ' trạm nguồn last_dept_name/scansitename)')
    print('   Backlog  map: ' + str(len(backlog_info_map)) + ' don (trạm đích, abnormal_remark & take_site_name từ Backlog JFS)')

    # ── Phase 5: Merge (FULL OUTER JOIN across all scan sources) ───────────────
    print('\nPhase 5 -- Merge (FULL OUTER JOIN all scan sources & deduplicate)...')
    df = pd.DataFrame(rows_v6)
    
    dispatch_trackings = set(df['tracking'].dropna().astype(str)) if not df.empty else set()
    all_scan_trackings = set(ib_scan_map.keys()) | set(ob_map.keys()) | set(arr_scan_map.keys())
    orphan_trackings   = all_scan_trackings - dispatch_trackings

    print('   Dispatch trackings : ' + str(len(dispatch_trackings)) + ' don')
    print('   Scan Log trackings : ' + str(len(all_scan_trackings)) + ' don')
    print('   Orphan Scans (Missing Dispatch): ' + str(len(orphan_trackings)) + ' don -> Generating fallback records...')

    orphan_rows = []
    for wb in orphan_trackings:
        inb_t  = ib_scan_map.get(wb, '')
        outb_t = ob_map.get(wb, '')
        arr_t  = arr_scan_map.get(wb, '')
        st_name = arr_station_map.get(wb) or ib_station_map.get(wb) or 'BN HUB'
        
        st_src = 'Outbound' if outb_t else ('Inbound' if inb_t else 'Arrival')

        cr_t = inb_t or outb_t or arr_t
        
        orphan_rows.append({
            'tracking': wb,
            'status_sys': st_src,
            'Created_time': cr_t,
            'Pickup_station': st_name,
            'Dispatch_code': '',
            'Orders_num': 1,
            'Orders_weight': 0.5,
            'Pickup_station2': '',
            'Pickup_time': '',
            'AreaCode': '',
            'flowTypeDesc': '',
            'Next_station': '',
            'Round': '',
            'Rank': 'Shuttle',
            'inbound_scanDate': inb_t,
            'outbound_scanDate': outb_t,
            'arrival_scanDate': arr_t,
            'trip_code': ib_trip_map.get(wb) or arr_trip_map.get(wb, ''),
            'transporing_time': '',
            'transported_time': '',
            'flag_no_dispatch': 1
        })

    if orphan_rows:
        df_orphans = pd.DataFrame(orphan_rows)
        df = pd.concat([df, df_orphans], ignore_index=True)

    df['inbound_scanDate']  = df.apply(lambda r: r.get('inbound_scanDate') or ib_scan_map.get(r['tracking'], ''), axis=1)
    df['outbound_scanDate'] = df.apply(lambda r: r.get('outbound_scanDate') or ob_map.get(r['tracking'], ''), axis=1)
    df['arrival_scanDate']  = df.apply(lambda r: r.get('arrival_scanDate') or arr_scan_map.get(r['tracking'], ''), axis=1)
    df['trip_code']         = df.apply(lambda r: r.get('trip_code') or ob_trip_map.get(r['tracking']) or ib_trip_map.get(r['tracking']) or arr_trip_map.get(r['tracking'], ''), axis=1)
    df['transporing_time']  = df.apply(lambda r: (ttm.get(r['trip_code'], {}).get('transporing_time', '') if r.get('trip_code') else '') or r.get('arrival_scanDate') or arr_scan_map.get(r['tracking'], ''), axis=1)
    df['transported_time']  = df['trip_code'].apply(lambda tc: ttm.get(tc, {}).get('transported_time', '') if tc else '')

    df['Pickup_station'] = df.apply(lambda r: arr_station_map.get(r['tracking']) or ib_station_map.get(r['tracking']) or r.get('Pickup_station') or 'BN HUB', axis=1)

    # 6 Lý do hoàn/trả hàng Backlog
    RETURN_REASONS = {
        'Số điện thoại không liên lạc được',
        'Người nhận từ chối nhận hàng',
        'Khách từ chối thanh toán',
        'Khách không đặt hàng',
        'Sai số điện thoại',
        'Người nhận đặt trùng đơn / mua nhầm'
    }

    # Waterfall Next_station, Round, Rank Lookup (Chính xác 6 bước theo yêu cầu cải tiến)
    def resolve_waterfall_next_station_round_rank(r):
        wb = str(r['tracking']).strip()
        sc = str(r.get('Dispatch_code') or '').strip().upper()
        ob_st = ob_next_station_map.get(wb, '')
        disp_st = str(r.get('Next_station') or '').strip()
        pk_st = str(r.get('Pickup_station') or '').strip()

        bl_info = backlog_info_map.get(wb, {})
        bl_dest = bl_info.get('dest', '')
        bl_rmk  = bl_info.get('remark', '')
        bl_take = bl_info.get('take_site', '')

        next_st = ''
        rnd = ''
        rnk = ''

        # Step 1: Match Dispatch_code -> sortcode valid.csv -> Station_2, Round, Rank
        if sc and dict_station.get(sc):
            next_st = dict_station[sc]
            rnd     = dict_round.get(sc, '')
            rnk     = dict_rank.get(sc, '')
        elif sc and len(sc) >= 6 and dict_station.get(sc[:6]):
            next_st = dict_station[sc[:6]]
            rnd     = dict_round.get(sc[:6], '')
            rnk     = dict_rank.get(sc[:6], '')

        # Step 6 (Inbound/Transporting/Backlog mapping với Backlog theo tracking):
        # Nếu abnormal_remark thuộc 6 lý do hoàn/trả -> lấy take_site_name, ngược lại lấy destination_site_name -> mapping Station_1 trong valid.csv ra Station_2
        if not next_st and bl_info:
            is_return = any(rr.lower() in bl_rmk.lower() for rr in RETURN_REASONS if bl_rmk and rr)
            target_bl_st = bl_take if (is_return and bl_take) else bl_dest

            if target_bl_st:
                tbl_upper = target_bl_st.upper()
                if dict_station.get(tbl_upper):
                    next_st = dict_station[tbl_upper]
                    rnd     = dict_round.get(tbl_upper, '')
                    rnk     = dict_rank.get(tbl_upper, '')
                elif target_bl_st not in ('', 'KHÔ VÙNG KHÁC', 'KHO VÙNG KHÁC', 'KHÁC', 'Chưa phân vùng'):
                    next_st = target_bl_st

        # Step 2: Fallback Backlog dest -> valid.csv (nếu chưa match được ở trên)
        if not next_st and bl_dest:
            bl_upper = bl_dest.upper()
            if dict_station.get(bl_upper):
                next_st = dict_station[bl_upper]
                rnd     = dict_round.get(bl_upper, '')
                rnk     = dict_rank.get(bl_upper, '')
            elif bl_dest not in ('', 'KHÔ VÙNG KHÁC', 'KHO VÙNG KHÁC', 'KHÁC', 'Chưa phân vùng'):
                next_st = bl_dest

        # Step 3: Giữ nguyên nextSite / nextNetworkName / receiveSite của Outbound
        if not next_st and ob_st:
            ob_upper = ob_st.upper()
            if dict_station.get(ob_upper):
                next_st = dict_station[ob_upper]
                rnd     = dict_round.get(ob_upper, '')
                rnk     = dict_rank.get(ob_upper, '')
            elif ob_st not in ('', 'KHÔ VÙNG KHÁC', 'KHO VÙNG KHÁC', 'KHÁC', 'Chưa phân vùng'):
                next_st = ob_st

        # Step 4: Miền Bắc (HN, BN, HD, HY...) -> Gán Linehaul/BN HUB nếu trạm nguồn thuộc Miền Bắc ngoài BN HUB
        pk_upper = pk_st.upper()
        if any(prefix in pk_upper for prefix in ['HN ', 'BN ', 'HD ', 'HY ']):
            if not next_st:
                next_st = 'BN HUB'
            if not rnd:
                rnd = 'Linehaul'
            if not rnk:
                rnk = 'BN HUB'

        # Step 5: Bỏ hoàn toàn việc gán nhầm Pickup_station -> Fallback chuẩn nếu không tìm thấy
        if not next_st:
            next_st = disp_st if disp_st else 'Chưa phân vùng'
        if not rnd:
            rnd = r.get('Round') or 'Shuttle'
        if not rnk:
            rnk = r.get('Rank') or rnd or 'FC'

        return pd.Series([next_st, rnd, rnk])

    mapped_res = df.apply(resolve_waterfall_next_station_round_rank, axis=1)
    df['Next_station'] = mapped_res[0]
    df['Round']        = mapped_res[1]
    df['Rank']         = mapped_res[2]

    # Cập nhật cột status_sys: Đơn hàng được lấy từ nguồn dữ liệu nào (Outbound, Inbound, Arrival, Backlog, Linehaul, Dispatch)
    def resolve_source_status_sys(r):
        wb = str(r['tracking']).strip()
        if r.get('outbound_scanDate') or ob_map.get(wb):
            return 'Outbound'
        if r.get('inbound_scanDate') or ib_scan_map.get(wb):
            return 'Inbound'
        if r.get('arrival_scanDate') or arr_scan_map.get(wb):
            return 'Arrival'
        if backlog_info_map.get(wb):
            return 'Backlog'
        if r.get('trip_code') and (r.get('transporing_time') or r.get('transported_time')):
            return 'Linehaul'
        return 'Dispatch'

    df['status_sys'] = df.apply(resolve_source_status_sys, axis=1)





    # ── Phase 6: PostgreSQL (psycopg2) ────────────────────────
    print('\nPhase 6 -- PostgreSQL (psycopg2)...')
    try:
        import psycopg2
        from psycopg2.extras import execute_values
        pg_db   = os.environ.get('PGDATABASE', 'logistics_db')
        passwords = ['Tien@giang0203', 'Tien@giang0203', 'postgres']
        conn = None
        for pwd in passwords:
            try:
                conn = psycopg2.connect(
                    host='127.0.0.1', port=5433, dbname=pg_db, user='postgres', password=pwd,
                    connect_timeout=10, options='-c statement_timeout=30000'
                )
                if conn: break
            except Exception:
                continue
        if not conn:
            raise Exception("Could not connect to PostgreSQL with any known password.")
        cur = conn.cursor()
        # FIX: Không dùng CASCADE để tránh rollback các bảng phụ thuộc
        try:
            cur.execute('TRUNCATE TABLE enriched.dispatch_enriched;')
        except Exception:
            conn.rollback()
            cur.execute('DELETE FROM enriched.dispatch_enriched;')

        records = []
        for _, r in df.iterrows():
            cr_t = str(r.get('Created_time') or r.get('created_time') or '').strip()
            inb_t = str(r.get('inbound_scanDate') or '').strip()
            outb_t = str(r.get('outbound_scanDate') or '').strip()
            arr_t = str(r.get('arrival_scanDate') or '').strip()

            op_cr = get_op_date(cr_t) if cr_t else ''
            op_inb = get_op_date(inb_t) if inb_t else ''

            has_in = bool(inb_t)
            has_out = bool(outb_t)
            is_backlog = 1 if (has_in and not has_out) else 0
            is_active = 0 if has_out else 1

            is_transit = 1 if (has_in and not has_out and bool(arr_t)) else 0

            # ── 4 ĐIỂM TINH CHỈNH KIẾN TRÚC REBOUND & FREEZING ───────
            is_rebound = 0
            return_count = 0
            cycle_no = 1
            inb_t_2 = None
            op_inb_2 = None
            outb_t_2 = None

            has_pick = bool(str(r.get('Pickup_time') or '').strip())
            has_transp = bool(str(r.get('transporing_time') or '').strip()) or bool(arr_t)

            # ═══════════════════════════════════════════════════════════════
            # NGUYÊN TẮC ĐÓNG BĂNG (Completed Order Freezing) — 2 Ưu tiên
            # ═══════════════════════════════════════════════════════════════
            # Ưu tiên 1 — Full Journey (đủ 5 mốc):
            #   Created → Pickup → Transporting → Inbound → Outbound
            priority_1 = bool(cr_t) and has_pick and has_transp and has_in and has_out

            # Ưu tiên 2 — HUB Completion tối thiểu (2 mốc HUB):
            #   Inbound + Outbound VÀ outbound_scandate > inbound_scandate
            priority_2 = has_in and has_out and (outb_t > inb_t)

            if has_out and inb_t and inb_t > outb_t:
                # Rebound: Đơn đã xuất kho Lần 1 nhưng phát hiện Inbound lần 2
                is_rebound = 1
                return_count = 1
                cycle_no = 2
                inb_t_2 = inb_t
                op_inb_2 = get_op_date(inb_t)
                is_completed = False  # Mở lại → nhảy vào Tồn bãi Rebound
                is_active = 1
                is_backlog = 1
            elif priority_1 or priority_2:
                # Đóng băng: thỏa ưu tiên 1 HOẶC ưu tiên 2
                is_completed = True
                is_active = 0
                is_backlog = 0
            else:
                is_completed = False

            # operation_date_created là NOT NULL → fallback sang target_date nếu rỗng
            op_cr_val = op_cr or str(r.get('Ngay_van_hanh') or r.get('Ngày vận hành') or '')[:10] or None
            if not op_cr_val and cr_t:
                op_cr_val = cr_t[:10]

            flag_created  = 1 if cr_t else 0
            flag_pickup   = 1 if has_pick else 0
            flag_arrival  = 1 if arr_t else 0
            flag_inbound  = 1 if has_in else 0
            flag_outbound = 1 if has_out else 0
            op_pk_val     = get_op_date(r.get('Pickup_time')) if has_pick else (op_cr_val or None)
            op_inb_eff    = op_inb_2 if (is_rebound and op_inb_2) else (op_inb or None)

            records.append((
                str(r.get('tracking') or ''),           # tracking NOT NULL
                'pipeline_v6',                           # data_source NOT NULL
                clean_status_sys(str(r.get('status_sys') or '')), # status_sys
                cr_t or None,                            # created_time
                str(r.get('Pickup_station') or ''),      # pickup_station
                str(r.get('Dispatch_code') or ''),       # dispatch_code
                int(r.get('Orders_num') or 1),           # orders_num
                float(r.get('Orders_weight') or 0.0),    # orders_weight
                str(r.get('Pickup_station2') or ''),     # pickup_station2
                str(r.get('Pickup_time') or '') or None, # pickup_time
                str(r.get('pickup_ontime') or ''),       # pickup_ontime
                str(r.get('AreaCode') or ''),            # areacode
                str(r.get('flowTypeDesc') or ''),        # flowtypedesc
                str(r.get('Next_station') or ''),        # next_station
                str(r.get('Round') or ''),               # round
                str(r.get('Rank') or ''),                # rank
                inb_t or None,                           # inbound_scandate
                outb_t or None,                          # outbound_scandate
                arr_t or None,                           # arrival_scandate
                str(r.get('trip_code') or ''),           # trip_code
                str(r.get('transporing_time') or '') or None,   # transporing_time
                str(r.get('transported_time') or '') or None,   # transported_time
                str(r.get('dispatch_actual') or ''),     # dispatch_actual
                op_cr_val,                               # operation_date_created
                op_inb or None,                          # operation_date_inbound
                is_backlog,                              # is_backlog
                is_active,                               # is_active
                is_transit,                              # is_transit
                is_completed,                            # is_completed
                cycle_no,                                # cycle_no
                is_rebound,                              # is_rebound
                return_count,                            # return_count
                inb_t_2,                                 # inbound_scandate_2
                op_inb_2,                                # operation_date_inbound_2
                outb_t_2,                                # outbound_scandate_2
                flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound,
                op_pk_val, op_inb_eff
            ))

        insert_sql = """
            INSERT INTO enriched.dispatch_enriched (
                tracking, data_source, status_sys, created_time,
                pickup_station, dispatch_code, orders_num, orders_weight,
                pickup_station2, pickup_time, pickup_ontime, areacode, flowtypedesc,
                next_station, round, rank,
                inbound_scandate, outbound_scandate, arrival_scandate,
                trip_code, transporing_time, transported_time, dispatch_actual,
                operation_date_created, operation_date_inbound,
                is_backlog, is_active, is_transit,
                is_completed, cycle_no, is_rebound, return_count,
                inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
                flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound,
                op_date_pickup, op_date_inbound_effective
            ) VALUES %s
            ON CONFLICT (tracking) DO UPDATE SET
                data_source              = EXCLUDED.data_source,
                status_sys               = EXCLUDED.status_sys,
                -- ═══════════════════════════════════════════════════════════
                -- NGUYÊN TẮC ĐÓNG BĂNG (Completed Order Freezing)
                -- ═══════════════════════════════════════════════════════════
                created_time             = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN enriched.dispatch_enriched.created_time       -- bảo vệ mốc gốc
                                            ELSE COALESCE(EXCLUDED.created_time, enriched.dispatch_enriched.created_time)
                                          END,
                pickup_time              = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN enriched.dispatch_enriched.pickup_time         -- bảo vệ mốc gốc
                                            ELSE COALESCE(EXCLUDED.pickup_time, enriched.dispatch_enriched.pickup_time)
                                          END,
                inbound_scandate         = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN enriched.dispatch_enriched.inbound_scandate    -- bảo vệ mốc gốc
                                            ELSE EXCLUDED.inbound_scandate
                                          END,
                outbound_scandate        = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN enriched.dispatch_enriched.outbound_scandate   -- bảo vệ mốc gốc
                                            ELSE EXCLUDED.outbound_scandate
                                          END,
                arrival_scandate         = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN enriched.dispatch_enriched.arrival_scandate    -- bảo vệ mốc gốc
                                            ELSE EXCLUDED.arrival_scandate
                                          END,
                is_completed             = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN TRUE                                           -- không cho phép downgrade
                                            ELSE EXCLUDED.is_completed
                                          END,
                is_active                = CASE
                                            WHEN enriched.dispatch_enriched.is_completed = TRUE
                                            THEN 0                                              -- frozen = inactive
                                            ELSE EXCLUDED.is_active
                                          END,
                pickup_station           = COALESCE(NULLIF(EXCLUDED.pickup_station, ''), enriched.dispatch_enriched.pickup_station),
                pickup_station2          = COALESCE(NULLIF(EXCLUDED.pickup_station2, ''), enriched.dispatch_enriched.pickup_station2),
                pickup_ontime            = COALESCE(NULLIF(EXCLUDED.pickup_ontime, ''), enriched.dispatch_enriched.pickup_ontime),
                areacode                 = COALESCE(NULLIF(EXCLUDED.areacode, ''), enriched.dispatch_enriched.areacode),
                flowtypedesc             = COALESCE(NULLIF(EXCLUDED.flowtypedesc, ''), enriched.dispatch_enriched.flowtypedesc),
                next_station             = EXCLUDED.next_station,
                trip_code                = EXCLUDED.trip_code,
                transporing_time         = EXCLUDED.transporing_time,
                transported_time         = EXCLUDED.transported_time,
                is_backlog               = EXCLUDED.is_backlog,
                is_transit               = EXCLUDED.is_transit,
                cycle_no                 = EXCLUDED.cycle_no,
                is_rebound               = EXCLUDED.is_rebound,
                return_count             = EXCLUDED.return_count,
                inbound_scandate_2       = COALESCE(EXCLUDED.inbound_scandate_2, enriched.dispatch_enriched.inbound_scandate_2),
                operation_date_inbound_2 = COALESCE(EXCLUDED.operation_date_inbound_2, enriched.dispatch_enriched.operation_date_inbound_2),
                outbound_scandate_2      = COALESCE(EXCLUDED.outbound_scandate_2, enriched.dispatch_enriched.outbound_scandate_2),
                flag_created             = EXCLUDED.flag_created,
                flag_pickup              = EXCLUDED.flag_pickup,
                flag_arrival             = EXCLUDED.flag_arrival,
                flag_inbound             = EXCLUDED.flag_inbound,
                flag_outbound            = EXCLUDED.flag_outbound,
                op_date_pickup           = EXCLUDED.op_date_pickup,
                op_date_inbound_effective= EXCLUDED.op_date_inbound_effective,
                last_updated             = CURRENT_TIMESTAMP;
        """
        execute_values(cur, insert_sql, records, page_size=2000)

        # Batch insert raw scan logs into raw.scan_logs (Append-Only Data Log)
        scan_log_records = []
        for r in raw.get('inbound', []):
            wb = clean_wb(r.get('billNo') or r.get('waybillNo'))
            st = str(r.get('scanDate') or '').strip()
            site = str(r.get('upOrNextStation') or r.get('sendSite') or r.get('sendNetworkName') or '').strip()
            tc = clean_wb(r.get('transferCode') or r.get('transfercode') or r.get('billTaskCode'))
            if wb and st and st.lower() not in ('nan', 'none', ''):
                scan_log_records.append((wb, 'INBOUND', st, site or None, tc or None, 1))

        for r in raw.get('outbound', []):
            wb = clean_wb(r.get('billNo') or r.get('waybillNo'))
            st = str(r.get('scanDate') or '').strip()
            if wb and st and st.lower() not in ('nan', 'none', ''):
                scan_log_records.append((wb, 'OUTBOUND', st, None, None, 1))

        if scan_log_records:
            log_sql = """
                INSERT INTO raw.scan_logs (tracking, scan_type, scan_time, station, trip_code, cycle_no)
                VALUES %s ON CONFLICT DO NOTHING;
            """
            execute_values(cur, log_sql, scan_log_records, page_size=2000)
            print(f"   raw.scan_logs: {len(scan_log_records):,} scan events recorded")

        conn.commit()
        cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched;")
        cnt = cur.fetchone()[0]
        conn.close()
        print(f"   ✅ PostgreSQL updated: {cnt:,} rows in enriched.dispatch_enriched")
    except Exception as e:
        print(f"   ⚠️  PostgreSQL error: {e}")

    # ── Phase 7: CSV ─────────────────────────────────────────
    print('\nPhase 7 -- Export CSV...')
    col_order = ['tracking','status_sys','Created_time',
                 'Pickup_station','Dispatch_code',
                 'Orders_num','Orders_weight',
                 'Pickup_station2','Pickup_time','AreaCode','flowTypeDesc',
                 'Next_station','Round','Rank',
                 'inbound_scanDate','outbound_scanDate','arrival_scanDate',
                 'trip_code','transporing_time','transported_time']
    # Giữ nguyên status_sys là tên Nguồn dữ liệu (Outbound, Inbound, Backlog, Arrival, Linehaul, Dispatch)
    df = df[[c for c in col_order if c in df.columns]]
    try:
        df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print('   DA LUU -> ' + OUTPUT_FILE)
    except PermissionError:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        alt = OUTPUT_FILE.replace('.csv', f'_{ts}.csv')
        try:
            df.to_csv(alt, index=False, encoding='utf-8-sig')
            print('   File đang mở -> lưu vào file mới: ' + alt)
        except Exception as e:
            print('   Bỏ qua lưu file CSV (PermissionError): ' + str(e))

    # ── Summary ──────────────────────────────────────────────
    total = len(df)
    print('\n' + '=' * 65)
    print('KET QUA PIPELINE UNIFIED V6')
    print('=' * 65)
    print('   Dispatch keo ve      : ' + str(len(raw.get('dispatch', []))))
    print('   Sau dedup/loc huy    : ' + str(total))

    if total > 0:
        def pct(col):
            target_col = next((c for c in df.columns if c.lower() == col.lower()), None)
            if not target_col: return '0 (0.0%)'
            n = (df[target_col].astype(str).str.strip() != '').sum()
            return str(n) + ' (' + str(round(n/total*100, 1)) + '%)'

        print('   Khop Inbound scan    : ' + pct('inbound_scanDate'))
        print('   Khop Outbound scan   : ' + pct('outbound_scanDate'))
        print('   Khop Arrival scan    : ' + pct('arrival_scanDate'))
        print('   Co trip_code         : ' + pct('trip_code'))
        print('   Co transporing_time  : ' + pct('transporing_time'))
        print('   Co transported_time  : ' + pct('transported_time'))
        print('   Co Next_station      : ' + pct('Next_station'))
    print('=' * 65)
    print('Tong thoi gian: ' + str(round(time.time() - t0, 1)) + 's')

if __name__ == '__main__':
    main()
