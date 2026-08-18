import sys, os, json, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb
)
from sync_postgre import get_pg_conn
import pandas as pd

print("🚀 [CHÍNH XÁC 100%] Đang kéo TOÀN BỘ đơn 'Đã hủy' (orderStatusCode = 104) từ JFS...")

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='CancelPull104')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=15)
base_pl['startInputTime'] = start_dt.strftime('%Y-%m-%d 00:00:00')
base_pl['endInputTime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')
base_pl['orderStatus'] = '104'
base_pl['orderStatusCode'] = '104'
base_pl['size'] = '100'
base_pl['current'] = '1'

# Kéo trang 1
r1 = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=base_pl, label='p1')
data1 = r1.json().get('data', {})
total_cancels = data1.get('total', 0)
n_pages = data1.get('pages', 1)
print(f"📦 JFS báo cáo có tổng cộng: {total_cancels:,} đơn ĐÃ HỦY ({n_pages} trang)")

all_cancelled_wbs = set()

recs1 = data1.get('records', []) or []
for r in recs1:
    wb = clean_wb(r.get('waybillId') or r.get('waybillNo') or r.get('tracking'))
    if wb:
        all_cancelled_wbs.add(wb)

# Kéo các trang tiếp theo với giãn cách 0.8s để bảo vệ server
for p in range(2, n_pages + 1):
    pl = dict(base_pl)
    pl['current'] = str(p)
    try:
        rp = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=pl, label=f'p{p}')
        obj = rp.json().get('data', {}) or {}
        recs = obj.get('records', []) or []
        for r in recs:
            wb = clean_wb(r.get('waybillId') or r.get('waybillNo') or r.get('tracking'))
            if wb:
                all_cancelled_wbs.add(wb)
        print(f"   Trang {p}/{n_pages}: +{len(recs)} đơn hủy (Lũy kế: {len(all_cancelled_wbs):,})")
    except Exception as e:
        print(f"   ⚠️ Lỗi trang {p}: {e}")
    time.sleep(0.8)

print(f"\n🎯 Đã thu thập thành công {len(all_cancelled_wbs):,} mã vận đơn ĐÃ HỦY từ JFS!")

# Cập nhật PostgreSQL
conn = get_pg_conn()
cur = conn.cursor()
canc_list = list(all_cancelled_wbs)

for i in range(0, len(canc_list), 500):
    batch = canc_list[i:i+500]
    batch_str = "('" + "','".join(batch) + "')"
    cur.execute(f"""
        UPDATE enriched.dispatch_enriched
        SET status_sys = 'Đã hủy'
        WHERE tracking IN {batch_str};
    """)

conn.commit()

# Kiểm tra bao nhiêu đơn BN HUB bị hủy
df_canc_bn = pd.read_sql("""
    SELECT tracking, status_sys, operation_date_created, pickup_station, next_station
    FROM enriched.dispatch_enriched
    WHERE status_sys = 'Đã hủy'
      AND (next_station = 'BN HUB' OR next_station LIKE 'HN %' OR next_station LIKE 'BN %')
      AND operation_date_created::date >= ('2026-08-18'::date - INTERVAL '15 days');
""", conn)
print(f"\n🏆 Số đơn 'Đã hủy' của riêng luồng BN HUB trong database: {len(df_canc_bn):,} đơn!")

conn.close()
print("🏁 Hoàn tất đồng bộ toàn bộ đơn hủy vào database.")
