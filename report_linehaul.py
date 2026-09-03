"""
report_linehaul.py — Luồng tự động tổng hợp Giám sát hàng đến (Đã đến) 10 ngày
                     mapping 1-đến-1 với Shuttle & Linehaul API, full 100% dữ liệu.

Chạy thủ công:
    python report_linehaul.py

Chạy có tuỳ chọn:
    python report_linehaul.py --days 10       # số ngày gần nhất (default=10)
    python report_linehaul.py --shuttle-start 2026-07-08  # ngày bắt đầu kéo Shuttle
    python report_linehaul.py --out output/MyReport.xlsx  # output file

Logic:
    1. Kéo Giám sát hàng đến (scanType=arr) từ realtime_sca_arr_mon_dtl
       - Theo chu kỳ vận hành 06:00-06:00 (cycle 6-6)
       - 10 ngày gần nhất, dedup theo [billcode + Ngày vận hành]
    2. Kéo Shuttle Live API (tmsBranchTrackingDetail/page)
       - Date range: shuttle_start → hôm nay + 1
       - Lập chỉ mục theo shipmentNo (PNV) → time_map
    3. Kéo Linehaul Live API (transport_consolidated_report)
       - Date range: shuttle_start → hôm nay + 1
       - Lập chỉ mục theo shipmentNo → time_map (ưu tiên sau Shuttle)
    4. Mapping 1-đến-1: transfercode → time_map
       - Fallback A: gio_den_thuc_te trống → lấy scantime sớm nhất của chuyến
       - Fallback B: gio_di_thuc_te trống → lấy gio_bat_dau_xep của chính dòng đó
    5. Xuất Excel 2 sheet: TongHop + ChiTiet_Full7Cot
"""

import os
import sys
import json
import argparse
import sqlite3
import time as _time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# ─── fix Unicode stdout trên Windows ───
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ─── resolve paths ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend_sync')
sys.path.insert(0, BACKEND_DIR)

from sync_to_sheets import (
    TokenManager, build_session,
    ACCOUNT, PASSWORD, COUNTRY_ID,
    VALID_FILE, load_valid, auth_post
)

# ─── constants ───
TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')

URL_INCOMING  = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'
URL_SHUTTLE   = 'https://gw.jtcargo.com.vn/transportation/tmsBranchTrackingDetail/page'
URL_LINEHAUL_REPORT = 'https://gw.jtcargo.com.vn/jfs-report-leader/report/dynamicReport/findByPagination'

INCOMING_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=UTF-8',
    'Origin': 'https://jfs.jtcargo.com.vn',
    'Referer': 'https://jfs.jtcargo.com.vn/',
    'routeName': 'Bd-theme-7aa50fd7-4558-418e-a69e-13bfa28fcc09|businessIndicatorIndex',
    'Routename': 'Bd-theme-7aa50fd7-4558-418e-a69e-13bfa28fcc09|businessIndicatorIndex',
    'lang': 'VN', 'langtype': 'VN',
    'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
}

SHUTTLE_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=UTF-8',
    'Origin': 'https://jfs.jtcargo.com.vn',
    'Referer': 'https://jfs.jtcargo.com.vn/',
    'routeName': 'BrancTaskTrackSearch1|businessIndicatorIndex',
    'Routename': 'BrancTaskTrackSearch1|businessIndicatorIndex',
    'lang': 'VN', 'langtype': 'VN',
}

LINEHAUL_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=UTF-8',
    'Origin': 'https://jfs.jtcargo.com.vn',
    'Referer': 'https://jfs.jtcargo.com.vn/',
    'routeName': 'Bd-table-bb3e578a-fa67-4587-8ed3-f69ec34aaab7|businessIndicatorIndex',
    'Routename': 'Bd-table-bb3e578a-fa67-4587-8ed3-f69ec34aaab7|businessIndicatorIndex',
    'lang': 'VN', 'langtype': 'VN',
}

INCOMING_PARAMS = {
    'sqlCode': 'realtime_sca_arr_mon_dtl',
    'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
}

LINEHAUL_PARAMS = {
    'sqlCode': 'transport_consolidated_report',
    'dcr_key': '57b048fb-bc8c-4d24-982b-a750b7ce8693',
}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def get_operating_date(dt_str: str) -> str:
    """Tính ngày vận hành theo cycle 6-6 (06:00 → 06:00 hôm sau)."""
    try:
        dt = datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
        if dt.hour < 6:
            dt -= timedelta(days=1)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return ''


def inject_token(headers: dict, token: str) -> dict:
    h = dict(headers)
    h['authToken'] = token
    h['Authtoken'] = token
    return h


def safe_get(r, timeout=20):
    try:
        return r.json()
    except Exception:
        return {}


def paginate_post(session, url, token_mgr, headers, payload, params=None, size=1000, label=''):
    """Generic paginator — trả về list tất cả records."""
    all_recs = []
    page = 1
    while True:
        p = {**payload, 'size': size, 'current': page}
        try:
            resp = auth_post(session, url, token_mgr, headers, json_body=p, params=params, label=f"{label} p{page}")
            raw_json = resp.json() if resp and hasattr(resp, 'json') else {}
            data = raw_json if isinstance(raw_json, dict) else {}
            node = data.get('data', {})
            recs = node.get('records', []) if isinstance(node, dict) else (node if isinstance(node, list) else [])
            if not recs:
                break
            all_recs.extend(recs)
            if len(recs) < size:
                break
            page += 1
        except Exception as e:
            print(f'   ⚠️  Lỗi {label} trang {page}: {e}')
            break
    return all_recs



# ═══════════════════════════════════════════════════════════════
# STEP 1 — Giám sát hàng đến (Đã đến) — 10 ngày cycle 6-6
# ═══════════════════════════════════════════════════════════════

def pull_incoming_10days(session, token_mgr, days=10):
    """Kéo Giám sát hàng đến day-by-day, dedup [billcode + Ngày vận hành]."""
    now = datetime.now(TZ_VN)
    now_naive = now.replace(tzinfo=None)

    # Tính ngày vận hành hôm nay theo cycle 6-6
    today_op = get_operating_date(now_naive.strftime('%Y-%m-%d %H:%M:%S'))
    start_op_dt = datetime.strptime(today_op, '%Y-%m-%d') - timedelta(days=days - 1)

    print(f'\n📅 Giám sát hàng đến — Pull {days} ngày vận hành')
    print(f'   Từ: {start_op_dt.strftime("%Y-%m-%d")} 06:00:00  →  Đến: {today_op} +1 ngày 06:00:00')

    base_payload = {
        'convertResultFromDictionCode': '',
        'convertResultFromDictionOriCode': '',
        'countryId': '1',
        'paginationSearchType': 'list',
        'scanSiteCode': 'HCM004H',
        'scanSiteCodeId': 11888,
        'scanSiteCodeName': 'HCM HUB',
        'scanSiteTypeId': 335,
        'scanType': 'arr',
        'sqlCode': 'realtime_sca_arr_mon_dtl',
        'wayType': '1',
    }

    all_rows = []
    cur = start_op_dt
    end_op_dt = datetime.strptime(today_op, '%Y-%m-%d') + timedelta(days=1)  # inclusive end day

    day_idx = 0
    while cur < end_op_dt:
        d_start = cur.strftime('%Y-%m-%d') + ' 06:00:00'
        d_end   = (cur + timedelta(days=1)).strftime('%Y-%m-%d') + ' 06:00:00'

        token = token_mgr.get_token()
        hdr = inject_token(INCOMING_HEADERS, token)

        page = 1
        day_count = 0
        while True:
            payload = {**base_payload, 'beginDate': d_start, 'endDate': d_end,
                       'size': 1000, 'current': page}
            try:
                resp = auth_post(session, URL_INCOMING, token_mgr, hdr,
                                 params=INCOMING_PARAMS, json_body=payload,
                                 label=f'Incoming {cur.strftime("%m/%d")} p{page}')
                raw_json = resp.json() if resp and hasattr(resp, 'json') else {}
                data = (raw_json or {}).get('data', {}) if isinstance(raw_json, dict) else {}
                recs = data.get('records', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if not recs:
                    break
                all_rows.extend(recs)
                day_count += len(recs)
                if len(recs) < 1000:
                    break
                page += 1
            except Exception as e:
                print(f'   ⚠️  Lỗi {cur.strftime("%Y-%m-%d")} trang {page}: {e}')
                break

        day_idx += 1
        print(f'   [{day_idx:02d}] {cur.strftime("%Y-%m-%d")} → {day_count:,} records')
        cur += timedelta(days=1)

    print(f'   ✅ Tổng raw: {len(all_rows):,} records')

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df.columns = df.columns.str.strip()

    # Rename common columns
    rename_map = {
        'billCode': 'billcode', 'scanTime': 'scantime',
        'transferCode': 'transfercode', 'lastDeptName': 'last_dept_name',
        'scanSiteName': 'scansitename', 'scanUser': 'scanuser',
        'packageChargeWeight': 'package_charge_weight',
        'packageNumber': 'package_number',
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    for col in ['billcode', 'scantime', 'transfercode', 'last_dept_name', 'scansitename',
                'package_charge_weight', 'package_number', 'scanuser']:
        if col not in df.columns:
            df[col] = ''

    df['scantime']     = df['scantime'].astype(str).str.strip()
    df['transfercode'] = df['transfercode'].astype(str).str.strip().str.upper()
    df['billcode']     = df['billcode'].astype(str).str.strip()
    df['Ngày vận hành'] = df['scantime'].apply(get_operating_date)
    df['Bưu cục gửi']  = df.get('last_dept_name', df.get('scansitename', ''))

    # Dedup theo [billcode + Ngày vận hành]
    before = len(df)
    df = df.sort_values('scantime').drop_duplicates(
        subset=['billcode', 'Ngày vận hành'], keep='first').reset_index(drop=True)
    print(f'   ✅ Sau dedup [billcode + Ngày vận hành]: {len(df):,} / {before:,} dòng')

    return df



# ═══════════════════════════════════════════════════════════════
# STEP 2 — Shuttle Live API index (shipmentNo → 7 cols)
# ═══════════════════════════════════════════════════════════════

def build_shuttle_index(session, token_mgr, start_date: str, end_date: str):
    """Kéo toàn bộ Shuttle API từ start_date → end_date, lập chỉ mục theo PNV."""
    print(f'\n🚚 Shuttle Live API: {start_date} → {end_date}')
    token = token_mgr.get_token()
    hdr = inject_token(SHUTTLE_HEADERS, token)

    time_map = {}
    cur = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while cur <= end:
        d_s = cur.strftime('%Y-%m-%d') + ' 00:00:00'
        d_e = cur.strftime('%Y-%m-%d') + ' 23:59:59'
        recs = paginate_post(session, URL_SHUTTLE, token_mgr, hdr,
                             {'startDepartureTime': d_s, 'endDepartureTime': d_e, 'countryId': '1'},
                             size=1000, label=f'Shuttle {cur.strftime("%m/%d")}')
        for row in recs:
            tc = str(row.get('shipmentNo') or '').strip().upper()
            if tc:
                time_map[tc] = {
                    'gio_bat_dau_xep': str(row.get('loadStartTime')        or '').strip(),
                    'gio_di_ke_hoach': str(row.get('plannedDepartureTime') or '').strip(),
                    'gio_den_ke_hoach': str(row.get('plannedArrivalTime')  or '').strip(),
                    'gio_di_thuc_te':  str(row.get('actualDepartureTime') or '').strip(),
                    'gio_den_thuc_te': str(row.get('actualArrivalTime')   or '').strip(),
                    'nguon_anh_xa':    'Shuttle',
                    'ETA Incoming':    str(row.get('estimateArrivalTime') or '').strip(),
                }
        cur += timedelta(days=1)

    print(f'   ✅ Chỉ mục Shuttle: {len(time_map):,} PNV duy nhất')
    return time_map


# ═══════════════════════════════════════════════════════════════
# STEP 3 — Linehaul Live API index
# ═══════════════════════════════════════════════════════════════

def build_linehaul_index(session, token_mgr, start_date: str, end_date: str):
    """Kéo toàn bộ Linehaul API từ start_date → end_date, lập chỉ mục theo PNV."""
    print(f'\n🚛 Linehaul Live API: {start_date} → {end_date}')
    token = token_mgr.get_token()
    hdr = inject_token(LINEHAUL_HEADERS, token)

    time_map = {}
    cur = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while cur <= end:
        d_s = cur.strftime('%Y-%m-%d') + ' 00:00:00'
        d_e = cur.strftime('%Y-%m-%d') + ' 23:59:59'
        recs = paginate_post(session, URL_LINEHAUL_REPORT, token_mgr, hdr,
                             {'startTime': d_s, 'endTime': d_e, 'timeType': '2', 'countryId': '1'},
                             params=LINEHAUL_PARAMS, size=1000,
                             label=f'Linehaul {cur.strftime("%m/%d")}')
        for row in recs:
            tc = str(row.get('shipmentNo') or '').strip().upper()
            if tc and tc not in time_map:  # Shuttle ưu tiên hơn
                time_map[tc] = {
                    'gio_bat_dau_xep': str(row.get('loadingScanStartTime')  or '').strip(),
                    'gio_di_ke_hoach': str(row.get('plannedDepartureTime')  or '').strip(),
                    'gio_den_ke_hoach': str(row.get('plannedArrivalTime')   or '').strip(),
                    'gio_di_thuc_te':  str(row.get('actualDepartureTime')  or '').strip(),
                    'gio_den_thuc_te': str(row.get('actualArrivalTime')    or '').strip(),
                    'nguon_anh_xa':    'Linehaul',
                    'ETA Incoming':    str(row.get('predictArriveTime')    or '').strip(),
                }
        cur += timedelta(days=1)

    print(f'   ✅ Chỉ mục Linehaul: {len(time_map):,} PNV duy nhất')
    return time_map



def load_local_csv_reports(time_map: dict):
    """Đọc thêm các báo cáo CSV cục bộ trong thư mục Desktop để bổ sung PNV."""
    import glob
    shuttle_csvs = glob.glob(r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\ReportShuttle\*.csv')
    linehaul_csvs = glob.glob(r'C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\ReportLinehaul\*.csv')
    
    cnt_st, cnt_lh = 0, 0
    
    print("\n📂 Đang quét thêm các file báo cáo CSV cục bộ...")
    for f in shuttle_csvs:
        try:
            df = pd.read_csv(f, dtype=str)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():
                tc = str(row.get('shipmentNo') or '').strip().upper()
                if tc and tc not in time_map:
                    time_map[tc] = {
                        'gio_bat_dau_xep': str(row.get('loadStartTime')        or '').strip(),
                        'gio_di_ke_hoach': str(row.get('plannedDepartureTime') or '').strip(),
                        'gio_den_ke_hoach': str(row.get('plannedArrivalTime')  or '').strip(),
                        'gio_di_thuc_te':  str(row.get('actualDepartureTime') or '').strip(),
                        'gio_den_thuc_te': str(row.get('actualArrivalTime')   or '').strip(),
                        'nguon_anh_xa':    'Shuttle (Local)',
                        'ETA Incoming':    str(row.get('estimateArrivalTime') or '').strip(),
                    }
                    cnt_st += 1
        except Exception:
            pass

    for f in linehaul_csvs:
        try:
            df = pd.read_csv(f, dtype=str)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():
                tc = str(row.get('shipmentNo') or '').strip().upper()
                if tc and tc not in time_map:
                    time_map[tc] = {
                        'gio_bat_dau_xep': str(row.get('loadingScanStartTime')  or '').strip(),
                        'gio_di_ke_hoach': str(row.get('plannedDepartureTime')  or '').strip(),
                        'gio_den_ke_hoach': str(row.get('plannedArrivalTime')   or '').strip(),
                        'gio_di_thuc_te':  str(row.get('actualDepartureTime')  or '').strip(),
                        'gio_den_thuc_te': str(row.get('actualArrivalTime')    or '').strip(),
                        'nguon_anh_xa':    'Linehaul (Local)',
                        'ETA Incoming':    str(row.get('predictArriveTime')    or '').strip(),
                    }
                    cnt_lh += 1
        except Exception:
            pass
            
    print(f"   ✅ Đã nạp thêm từ CSV cục bộ: {cnt_st} PNV Shuttle, {cnt_lh} PNV Linehaul")



# ═══════════════════════════════════════════════════════════════
# STEP 4 — Enrich + fallback logic
# ═══════════════════════════════════════════════════════════════

def enrich(df: pd.DataFrame, time_map: dict, d_rank: dict) -> pd.DataFrame:
    """Map 7 cột thời gian xe chạy vào df, xử lý fallback A & B."""

    cols = ['gio_bat_dau_xep', 'gio_di_ke_hoach', 'gio_den_ke_hoach',
            'gio_di_thuc_te', 'gio_den_thuc_te', 'nguon_anh_xa', 'ETA Incoming']
    for c in cols:
        df[c] = ''

    tcs = df['transfercode'].astype(str).str.strip().str.upper()

    for col_name, api_key in [
        ('gio_bat_dau_xep',  'gio_bat_dau_xep'),
        ('gio_di_ke_hoach',  'gio_di_ke_hoach'),
        ('gio_den_ke_hoach', 'gio_den_ke_hoach'),
        ('gio_di_thuc_te',   'gio_di_thuc_te'),
        ('gio_den_thuc_te',  'gio_den_thuc_te'),
        ('nguon_anh_xa',     'nguon_anh_xa'),
        ('ETA Incoming',     'ETA Incoming'),
    ]:
        df[col_name] = tcs.map(lambda tc: time_map.get(tc, {}).get(api_key, ''))

    # Fallback A: gio_den_thuc_te trống → scantime sớm nhất của chuyến
    df['_scantime_dt'] = pd.to_datetime(df['scantime'], errors='coerce')
    min_scan = df.groupby('transfercode')['_scantime_dt'].min()
    min_scan_str = min_scan.dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    mask_arr = df['gio_den_thuc_te'].isna() | (df['gio_den_thuc_te'].astype(str).str.strip() == '')
    df.loc[mask_arr, 'gio_den_thuc_te'] = df.loc[mask_arr, 'transfercode'].map(min_scan_str)
    df.loc[mask_arr & (df['nguon_anh_xa'] == ''), 'nguon_anh_xa'] = 'Giám sát hàng đến (scantime Min)'

    # Fallback B: gio_di_thuc_te trống → gio_bat_dau_xep của chính dòng
    mask_dep = df['gio_di_thuc_te'].isna() | (df['gio_di_thuc_te'].astype(str).str.strip().isin(['', 'nan']))
    df.loc[mask_dep, 'gio_di_thuc_te'] = df.loc[mask_dep, 'gio_bat_dau_xep']

    # ✅ Tạo cột các đơn được inbound sau 6H sáng và trước 1H sáng hôm sau (tiếng 6-23 và tiếng 0)
    hours = df['_scantime_dt'].dt.hour
    df['inbound_6h_1h'] = ((hours >= 6) | (hours < 1)).astype(int)

    df.drop(columns=['_scantime_dt'], inplace=True)



    # Rank
    def _rank(row):
        station = str(row.get('last_dept_name') or row.get('scansitename') or '').strip().upper()
        nguon   = str(row.get('nguon_anh_xa') or '').strip().lower()
        if station == 'BN HUB' or nguon == 'linehaul':
            return 'Linehaul'
        if d_rank.get(station, '') in ('Linehaul', 'BN HUB'):
            return 'Linehaul'
        if station.startswith('HN ') or station.startswith('HD ') or station.startswith('HY '):
            return 'Linehaul'
        return 'Shuttle'

    df['Rank'] = df.apply(_rank, axis=1)

    # Bưu cục gửi
    if 'Bưu cục gửi' not in df.columns:
        df['Bưu cục gửi'] = df.get('last_dept_name', df.get('scansitename', ''))

    return df


# ═══════════════════════════════════════════════════════════════
# STEP 5 — Export
# ═══════════════════════════════════════════════════════════════

def export(df: pd.DataFrame, excel_path: str):
    billcode_col = 'billcode' if 'billcode' in df.columns else 'billNo'

    front_cols = [
        billcode_col, 'Ngày vận hành', 'Rank', 'Bưu cục gửi', 'scansitename', 'transfercode',
        'inbound_6h_1h',
        'gio_bat_dau_xep', 'gio_di_ke_hoach', 'gio_den_ke_hoach',
        'gio_di_thuc_te', 'gio_den_thuc_te', 'nguon_anh_xa', 'ETA Incoming',
        'package_charge_weight', 'package_number', 'scanuser', 'scantime',
    ]
    skip = {'_scantime_dt', 'scantime_dt', 'weight_num'}
    other = [c for c in df.columns if c not in front_cols and c not in skip]
    final_cols = [c for c in front_cols if c in df.columns] + other
    df_export = df[final_cols]

    # ✅ Tạo df_summary định dạng chính xác theo yêu cầu (Ngày vận hành, Bưu cục gửi, transfercode, gio_di_thuc_te, gio_den_thuc_te, Count of billcode)
    df_summary = (
        df.groupby(['Ngày vận hành', 'Bưu cục gửi', 'transfercode', 'gio_di_thuc_te', 'gio_den_thuc_te'], dropna=False)
        .agg(**{'Count of billcode': (billcode_col, 'count')})
        .reset_index()
    )
    df_summary.fillna('', inplace=True)


    os.makedirs(os.path.dirname(excel_path), exist_ok=True)

    # Tránh lỗi permission nếu file đang mở
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='TongHop', index=False)
            df_export.to_excel(writer, sheet_name='ChiTiet_Full7Cot', index=False)
    except PermissionError:
        ts = datetime.now().strftime('%H%M%S')
        fallback = excel_path.replace('.xlsx', f'_tmp{ts}.xlsx')
        with pd.ExcelWriter(fallback, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='TongHop', index=False)
            df_export.to_excel(writer, sheet_name='ChiTiet_Full7Cot', index=False)
        excel_path = fallback
        print(f'   ⚠️  File đang mở → xuất sang: {fallback}')

    size_mb = os.path.getsize(excel_path) / 1024 / 1024
    print(f'\n💾 Xuất xong: {excel_path}  ({size_mb:.2f} MB)')
    return excel_path


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='report_linehaul — Giám sát hàng đến full 100%')
    parser.add_argument('--days', type=int, default=10,
                        help='Số ngày vận hành gần nhất (default=10)')
    parser.add_argument('--shuttle-start', type=str, default=None,
                        help='Ngày bắt đầu kéo Shuttle/Linehaul API (YYYY-MM-DD), '
                             'default = today - days - 3 (để bắt trọn xe xuất phát sớm)')
    parser.add_argument('--out', type=str,
                        default=os.path.join(BASE_DIR, 'output', 'GiamSatHangDen_DaDen_10Ngay_Final.xlsx'),
                        help='Đường dẫn file Excel output')
    args = parser.parse_args()

    now = datetime.now(TZ_VN)
    today_op = get_operating_date(now.strftime('%Y-%m-%d %H:%M:%S'))

    # Shuttle/Linehaul date range: bắt đầu 3 ngày trước điểm kéo Incoming để đảm bảo xe xuất phát sớm vẫn được bắt
    if args.shuttle_start:
        shuttle_start = args.shuttle_start
    else:
        shuttle_start = (datetime.strptime(today_op, '%Y-%m-%d') - timedelta(days=args.days + 2)).strftime('%Y-%m-%d')
    shuttle_end = (datetime.strptime(today_op, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

    # ✅ Đăng nhập với tài khoản có quyền truy cập rộng rãi trên hệ thống (Full Post Offices Scope)
    ADMIN_ACCOUNT = '660085'
    ADMIN_PASSWORD = 'Hoang@246'

    print('=' * 65)
    print('  report_linehaul.py — Giám sát hàng đến Full 100%')
    print(f'  Chạy lúc: {now.strftime("%Y-%m-%d %H:%M:%S")} (VN)')
    print(f'  Tài khoản: {ADMIN_ACCOUNT} (Quyền rộng)')
    print(f'  Số ngày  : {args.days} ngày vận hành')
    print(f'  Shuttle  : {shuttle_start} → {shuttle_end}')
    print(f'  Output   : {args.out}')
    print('=' * 65)

    t0 = _time.time()

    # Auth
    session = build_session()
    token_mgr = TokenManager(session, ADMIN_ACCOUNT, ADMIN_PASSWORD, COUNTRY_ID)
    token_mgr.get_token()  # pre-warm

    # Load valid rank mapping
    _, _, _, d_rank = load_valid(VALID_FILE)

    # Step 1 — Kéo Giám sát hàng đến (dùng tài khoản liên kết ban đầu)
    df_main = pull_incoming_10days(session, token_mgr, days=args.days)
    if df_main.empty:
        print('❌ Không có dữ liệu Giám sát hàng đến — dừng.')
        return

    # Step 2 & 3 — Build time index từ Shuttle + Linehaul Live API
    shuttle_idx = build_shuttle_index(session, token_mgr, shuttle_start, shuttle_end)
    linehaul_idx = build_linehaul_index(session, token_mgr, shuttle_start, shuttle_end)

    # Merge: Shuttle trước, Linehaul bổ sung những PNV chưa có
    time_map = {**linehaul_idx, **shuttle_idx}  # Shuttle override Linehaul

    # Thống kê & Thực hiện Query trực tiếp đối với các PNV chưa khớp (Live API fallback - Tự động bổ sung phiếu thiếu)
    all_pnv = set(df_main['transfercode'].dropna().astype(str).str.strip().str.upper().unique())
    matched = all_pnv.intersection(set(time_map.keys()))
    unmatched = list(all_pnv - set(time_map.keys()))

    if unmatched:
        print(f'\n🔍 Tìm thấy {len(unmatched)} PNV chưa khớp. Tiến hành truy vấn tự động từng phiếu qua API...')
        for pnv in unmatched:
            token = token_mgr.get_token()
            found_pnv = False

            # 1. Fallback query Shuttle API
            try:
                hdr_st = inject_token(SHUTTLE_HEADERS, token)
                payload_st = {
                    'shipmentNos': [pnv],
                    'startDepartureTime': '2026-07-01 00:00:00',
                    'endDepartureTime': (now + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
                    'countryId': '1',
                    'size': 10,
                    'current': 1
                }
                r = session.post(URL_SHUTTLE, headers=hdr_st, json=payload_st, timeout=15)
                recs = r.json().get('data', {}).get('records', []) if isinstance(r.json().get('data'), dict) else []
                if recs:
                    row = recs[0]
                    time_map[pnv] = {
                        'gio_bat_dau_xep': str(row.get('loadStartTime')        or '').strip(),
                        'gio_di_ke_hoach': str(row.get('plannedDepartureTime') or '').strip(),
                        'gio_den_ke_hoach': str(row.get('plannedArrivalTime')  or '').strip(),
                        'gio_di_thuc_te':  str(row.get('actualDepartureTime') or '').strip(),
                        'gio_den_thuc_te': str(row.get('actualArrivalTime')   or '').strip(),
                        'nguon_anh_xa':    'Shuttle (API Fallback)',
                        'ETA Incoming':    str(row.get('estimateArrivalTime') or '').strip(),
                    }
                    found_pnv = True
                    print(f'   ✅ Tìm thấy {pnv} qua Shuttle API Fallback')
            except Exception as e_st:
                pass

            if found_pnv:
                continue

            # 2. Fallback query Linehaul traceSub API
            try:
                hdr_tr = inject_token(LINEHAUL_HEADERS, token)
                # Dùng endpoint queryTraceSubForPage của Linehaul
                url_tr = 'https://gw.jtcargo.com.vn/operatingplatform/traceSub/queryTraceSubForPage'
                payload_tr = {
                    'traceCodes': [pnv],
                    'startScanTime': '2026-07-01 00:00:00',
                    'endScanTime': (now + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
                    'countryId': '1',
                    'searchType': 1,
                    'size': 10,
                    'current': 1
                }
                r = session.post(url_tr, headers=hdr_tr, json=payload_tr, timeout=15)
                recs = r.json().get('data', {}).get('records', []) if isinstance(r.json().get('data'), dict) else []
                if recs:
                    row = recs[0]
                    time_map[pnv] = {
                        'gio_bat_dau_xep': str(row.get('loadingScanStartTime')  or '').strip(),
                        'gio_di_ke_hoach': str(row.get('plannedDepartureTime')  or '').strip(),
                        'gio_den_ke_hoach': str(row.get('plannedArrivalTime')   or '').strip(),
                        'gio_di_thuc_te':  str(row.get('actualDepartureTime')  or '').strip(),
                        'gio_den_thuc_te': str(row.get('actualArrivalTime')    or '').strip(),
                        'nguon_anh_xa':    'Linehaul (API Fallback)',
                        'ETA Incoming':    str(row.get('predictArriveTime')    or '').strip(),
                    }
                    print(f'   ✅ Tìm thấy {pnv} qua Linehaul API Fallback')
            except Exception as e_tr:
                pass

        # Tái đánh giá lại kết quả khớp
        matched = all_pnv.intersection(set(time_map.keys()))
        unmatched = list(all_pnv - set(time_map.keys()))

    print(f'\n📊 Kết quả mapping PNV 1-đến-1 trực tiếp từ API:')
    print(f'   Tổng PNV duy nhất trong Giám sát hàng đến : {len(all_pnv):,}')
    print(f'   Khớp từ Shuttle + Linehaul API             : {len(matched):,}  ({len(matched)/len(all_pnv):.1%})')
    print(f'   Chưa khớp (sẽ fallback scantime)           : {len(unmatched):,}  ({len(unmatched)/len(all_pnv):.1%})')
    if unmatched:
        print(f'   PNV chưa khớp: {sorted(unmatched)[:10]}{"..." if len(unmatched) > 10 else ""}')

    # Step 4 — Enrich
    df_main = enrich(df_main, time_map, d_rank)

    # Final check
    empty_dep = (df_main['gio_di_thuc_te'].isna() | df_main['gio_di_thuc_te'].astype(str).str.strip().isin(['', 'nan'])).sum()
    empty_arr = (df_main['gio_den_thuc_te'].isna() | df_main['gio_den_thuc_te'].astype(str).str.strip().isin(['', 'nan'])).sum()
    total = len(df_main)
    print(f'\n✅ Kết quả sau fallback:')
    print(f'   Tổng vận đơn          : {total:,}')
    print(f'   gio_di_thuc_te  trống : {empty_dep:,}  ({empty_dep/total:.1%})')
    print(f'   gio_den_thuc_te trống : {empty_arr:,}  ({empty_arr/total:.1%})')

    # Step 5 — Export
    export(df_main, args.out)

    elapsed = _time.time() - t0
    print(f'\n⏱  Tổng thời gian: {elapsed:.1f}s')
    print('=' * 65)


if __name__ == '__main__':
    main()


