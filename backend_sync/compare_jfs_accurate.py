import os
import sys
import json
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from sync_to_sheets import (
    load_json, TokenManager, pull_forecast,
    LOGIN_URL, ACCOUNT, PASSWORD
)

def check_jfs():
    tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
    now = datetime.now(tz_vn)
    
    # Kéo dữ liệu từ ngày 2026-07-17 đến nay (4 ngày)
    date_start = "2026-07-17 00:00:00"
    date_end = now.strftime('%Y-%m-%d %H:%M:%S')
    
    print("🔐 Đăng nhập JFS API...")
    session = requests.Session()
    token_mgr = TokenManager(session, LOGIN_URL, ACCOUNT, PASSWORD)
    
    if not token_mgr.get_token():
        print("❌ Login thất bại!")
        return
        
    print(f"📡 Kéo dữ liệu Forecast từ JFS ({date_start} → {date_end})...")
    fh = load_json(os.path.join(BASE_DIR, "config", "forecastheaders.json"))
    fp = load_json(os.path.join(BASE_DIR, "config", "forecastpayload.json"))
    fp['beginDate'] = date_start
    fp['endDate'] = date_end
    
    jfs_fc = pull_forecast(session, token_mgr, fh, fp)
    print(f"✅ JFS Forecast API trả về: {len(jfs_fc):,} dòng")
    
    # Nhóm theo ngày vận hành Forecast từ JFS
    records = []
    for r in jfs_fc:
        wb = r.get('waybillNo') or r.get('billNo') or ''
        station = r.get('pickNetworkName') or ''
        status = r.get('status') or ''
        disp_time = r.get('dispatchNetworkTime') or r.get('networkTime') or ''
        pk_time = r.get('pickupTime') or ''
        
        # Chỉ check bưu cục khác BN HUB
        if (station or '').strip().upper() == 'BN HUB':
            continue
            
        # Lấy ngày vận hành
        fc_date = ""
        if disp_time and len(disp_time) >= 13:
            hr = int(disp_time[11:13])
            if hr < 6:
                fc_date = (datetime.strptime(disp_time[:10], '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                fc_date = disp_time[:10]
        
        records.append({
            'waybill': wb,
            'status': status,
            'station': station,
            'fc_date': fc_date,
            'pk_time': pk_time
        })
        
    df_jfs = pd.DataFrame(records)
    print(f"\nPhân tích JFS Forecast theo ngày:")
    if not df_jfs.empty:
        summary = df_jfs.groupby(['fc_date', 'status']).size().unstack(fill_value=0)
        print(summary.to_string())
    else:
        print("Không có record nào.")

if __name__ == "__main__":
    check_jfs()
