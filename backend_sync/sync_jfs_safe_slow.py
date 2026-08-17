import sys, os, json, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb,
    clean_status_sys, sql_esc, get_op_date
)
from sync_postgre import get_pg_conn

print("🚀 [CHẾ ĐỘ AN TOÀN] Đồng bộ trạng thái Dispatch từ JFS API (Tốc độ chậm, 1 req/s)...")

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='SlowDispatchSync')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=7)
base_pl['startInputTime'] = start_dt.strftime('%Y-%m-%d 00:00:00')
base_pl['endInputTime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')
base_pl['size'] = 100
base_pl['current'] = 1

cancel_updates = []
seen_wbs = set()

# Quét qua 50 trang đầu tiên (5,000 đơn mới nhất)
for p in range(1, 60):
    pl = dict(base_pl)
    pl['current'] = str(p)
    try:
        rp = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=pl, label=f'p{p}')
        res_json = rp.json()
        obj = res_json.get('data') or {}
        if isinstance(obj, str):
            try: obj = json.loads(obj)
            except: obj = {}
        if not isinstance(obj, dict):
            continue
            
        recs = obj.get('records') or obj.get('list') or obj.get('rows') or []
        if not recs:
            break
            
        page_cancels = 0
        for r in recs:
            wb = clean_wb(r.get('waybillId') or r.get('waybillNo'))
            st_raw = str(r.get('orderStatusName') or '')
            st_sys = clean_status_sys(st_raw)
            if st_sys == 'Đã hủy' and wb and (wb not in seen_wbs):
                seen_wbs.add(wb)
                cancel_updates.append(wb)
                page_cancels += 1
                
        print(f"   Trang {p}: +{len(recs)} đơn | Trang này có {page_cancels} đơn hủy (Lũy kế hủy: {len(cancel_updates)})")
    except Exception as e:
        print(f"   ⚠️ Trang {p} lỗi: {e}")
        time.sleep(2.0)
    time.sleep(1.0) # Nghỉ 1.0s giữa các request

print(f"\n🎯 Hoàn tất quét JFS! Tìm thấy tổng cộng: {len(cancel_updates)} đơn ĐÃ HỦY.")

if cancel_updates:
    print("🔄 Đang cập nhật trạng thái 'Đã hủy' vào PostgreSQL database...")
    conn = get_pg_conn()
    cur = conn.cursor()
    
    # Cập nhật theo batch 500
    for i in range(0, len(cancel_updates), 500):
        batch = cancel_updates[i:i+500]
        batch_str = "('" + "','".join(batch) + "')"
        cur.execute(f"""
            UPDATE enriched.dispatch_enriched
            SET status_sys = 'Đã hủy'
            WHERE tracking IN {batch_str};
        """)
    conn.commit()
    conn.close()
    print(f"✅ Đã cập nhật thành công {len(cancel_updates)} đơn HỦY vào database!")

print("🏁 Xong bước đồng bộ trạng thái hủy.")
