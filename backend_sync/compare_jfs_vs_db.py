"""
So sánh waybill-by-waybill:
  - Source A: JFS Forecast API (19.664 đơn dashboard đang hiển thị)
  - Source B: DB active Forecast (16.176 đơn)
Output:
  - File 1: Có trên JFS nhưng KHÔNG có trong DB active (thiếu)
  - File 2: Có trong DB active nhưng KHÔNG có trên JFS (thừa)
"""
import os, sys, json, sqlite3, requests, time
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Import helpers từ sync script
from sync_to_sheets import (
    load_json, TokenManager, URL_FORECAST,
    pull_forecast, LOGIN_URL, ACCOUNT, PASSWORD
)


tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
now = datetime.now(tz_vn)

# Op date range
if now.hour < 6:
    op_start = (now - timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
else:
    op_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
op_end = op_start + timedelta(hours=24)

date_start = (op_start - timedelta(days=1)).strftime('%Y-%m-%d') + ' 06:00:00'  # kéo 2 ngày
date_end   = now.strftime('%Y-%m-%d %H:%M:%S')

print(f"🔐 Đang login JFS...")
session = requests.Session()
token_mgr = TokenManager(session, LOGIN_URL, ACCOUNT, PASSWORD)

if not token_mgr.get_token():
    print("❌ Không login được!")
    sys.exit(1)

print(f"📡 Kéo Forecast từ JFS ({date_start} → {date_end})...")
fh = load_json(os.path.join(BASE_DIR, "config", "forecastheaders.json"))
fp = load_json(os.path.join(BASE_DIR, "config", "forecastpayload.json"))
fp['beginDate'] = date_start
fp['endDate']   = date_end

raw_fc = pull_forecast(session, token_mgr, fh, fp)
print(f"✅ JFS trả về: {len(raw_fc):,} đơn")

# Lấy set waybill từ JFS
jfs_wbs = {str(r.get('waybillNo') or r.get('billNo') or '').strip() for r in raw_fc}
jfs_wbs.discard('')

# Source B: DB active Forecast
conn = sqlite3.connect(os.path.join(BASE_DIR, "db", "state.db"))
df_db = pd.read_sql_query("""
    SELECT waybillNo, status_order, pickNetworkName, next_station,
           dispatch_plan, Pickup_time, dispatchNetworkTime,
           inbound_scanDate, outbound_scanDate, weight, time_ref
    FROM shipments
    WHERE data_source = 'Forecast' AND is_active = 1
""", conn)
conn.close()

db_wbs = set(df_db['waybillNo'].astype(str).str.strip())

# --- So sánh ---
only_in_jfs = jfs_wbs - db_wbs   # Có trên JFS nhưng thiếu trong DB
only_in_db  = db_wbs - jfs_wbs   # Có trong DB nhưng JFS không trả về

print(f"\n📊 KẾT QUẢ SO SÁNH:")
print(f"   JFS Forecast API:    {len(jfs_wbs):,} waybill")
print(f"   DB Active Forecast:  {len(db_wbs):,} waybill")
print(f"   Trùng nhau:          {len(jfs_wbs & db_wbs):,} waybill")
print(f"   Có trên JFS, thiếu DB: {len(only_in_jfs):,} ← FILE 1")
print(f"   Có trong DB, thiếu JFS: {len(only_in_db):,} ← FILE 2")

# FILE 1: Có trên JFS nhưng không trong DB active
jfs_rows = [r for r in raw_fc if str(r.get('waybillNo') or r.get('billNo') or '').strip() in only_in_jfs]
df_file1 = pd.DataFrame([{
    'Mã vận đơn':       str(r.get('waybillNo') or r.get('billNo') or ''),
    'Bưu cục lấy hàng': str(r.get('pickNetworkName') or ''),
    'Điểm đến':         str(r.get('nextStation') or r.get('next_station') or ''),
    'TG Forecast':      str(r.get('dispatchNetworkTime') or r.get('networkTime') or ''),
    'TG Lấy hàng':      str(r.get('pickupTime') or ''),
    'Trạng thái JFS':   str(r.get('status') or ''),
    'KL (kg)':          r.get('weight', 0),
} for r in jfs_rows])
df_file1.to_csv('data/FILE1_JFS_co_DB_khong.csv', index=False, encoding='utf-8-sig')

# FILE 2: Có trong DB nhưng không trên JFS
df_file2 = df_db[df_db['waybillNo'].isin(only_in_db)].copy()
df_file2.columns = ['Mã vận đơn', 'Trạng thái DB', 'Bưu cục lấy hàng', 'Điểm đến',
                    'Tuyến', 'TG Lấy hàng', 'TG Forecast', 'TG Inbound', 'TG Outbound',
                    'KL (kg)', 'Ngày tham chiếu']
df_file2.to_csv('data/FILE2_DB_co_JFS_khong.csv', index=False, encoding='utf-8-sig')

print(f"\n💾 Đã lưu:")
print(f"   FILE1_JFS_co_DB_khong.csv  ({len(df_file1):,} đơn)")
print(f"   FILE2_DB_co_JFS_khong.csv  ({len(df_file2):,} đơn)")
