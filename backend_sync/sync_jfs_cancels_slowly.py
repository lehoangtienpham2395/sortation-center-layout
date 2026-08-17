import sys, os, json, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, URL_FORECAST,
    cfg, clean_wb
)
from sync_postgre import get_pg_conn
import pandas as pd

print("🚀 Bắt đầu đồng bộ trạng thái đơn hủy từ JFS API (Chế độ CHẬM & AN TOÀN)...")

# 1. Khởi tạo Session và Token Manager
session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='CancelSync')
headers = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://jfs.jtcargo.com.vn',
    'Referer': 'https://jfs.jtcargo.com.vn/',
    'lang': 'VN', 'langtype': 'VN',
    'routeName': 'orderDispatch',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# 2. Lấy danh sách 3,086 mã đơn BN HUB từ database
conn = get_pg_conn()
df_bn = pd.read_sql("""
    SELECT tracking, status_sys, operation_date_created, pickup_station, next_station
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND (next_station = 'BN HUB' OR next_station LIKE 'HN %' OR next_station LIKE 'BN %')
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)
conn.close()

billcodes = [str(x).strip() for x in df_bn['tracking'] if str(x).strip()]
print(f"📦 Đang kiểm tra trạng thái cho {len(billcodes):,} mã vận đơn BN HUB...")

# 3. Quét qua JFS API với batch size 50 và time.sleep(1.0) để không gây áp lực lên server JFS
batch_size = 50
canceled_billcodes = []
status_counts = {}

# Thử truy vấn qua URL_DISPATCH với tham số billCode/waybillNo
for i in range(0, len(billcodes), batch_size):
    batch = billcodes[i:i+batch_size]
    batch_str = ','.join(batch)
    
    pl = {
        'current': 1,
        'size': batch_size,
        'waybillNo': batch_str,
        'billCode': batch_str
    }
    
    try:
        r = auth_post(session, URL_DISPATCH, token_mgr, headers, data=pl, label=f'Batch {i//batch_size + 1}')
        res = r.json()
        data_obj = res.get('data') or {}
        recs = data_obj.get('records') or data_obj.get('list') or data_obj.get('rows') or []
        
        for rec in recs:
            wb = clean_wb(rec.get('waybillNo') or rec.get('billCode') or rec.get('tracking'))
            st_name = str(rec.get('orderStatusName') or rec.get('billStatusName') or rec.get('statusName') or rec.get('orderStatus') or '').strip()
            st_code = str(rec.get('orderStatus') or rec.get('status') or '')
            
            status_counts[st_name] = status_counts.get(st_name, 0) + 1
            
            # Kiểm tra trạng thái HỦY
            is_canc = any(kw in st_name.lower() for kw in ['hủy', 'cancel', 'da huy']) or (st_code in ('99', 'CANCEL', 'CANCELLED', 'HỦY'))
            if is_canc and wb:
                canceled_billcodes.append(wb)
                
    except Exception as e:
        print(f"   ⚠️ Lỗi batch {i//batch_size + 1}: {e}")
        
    # Giãn cách 0.8s - 1.0s mỗi request theo yêu cầu người dùng
    time.sleep(0.8)

print(f"\n📊 Tổng hợp kết quả từ JFS API:")
print(f"   - Số đơn đã quét: {len(billcodes)}")
print(f"   - Phân bố trạng thái: {status_counts}")
print(f"   - Phát hiện {len(canceled_billcodes)} đơn ĐÃ HỦY!")

# 4. Nếu tìm thấy đơn hủy, cập nhật ngay vào PostgreSQL
if canceled_billcodes:
    conn_up = get_pg_conn()
    cur = conn_up.cursor()
    canc_set_str = "('" + "','".join(canceled_billcodes) + "')"
    cur.execute(f"""
        UPDATE enriched.dispatch_enriched
        SET status_sys = 'Đã hủy'
        WHERE tracking IN {canc_set_str};
    """)
    conn_up.commit()
    conn_up.close()
    print(f"✅ Đã cập nhật trạng thái 'Đã hủy' cho {len(canceled_billcodes)} đơn trong database!")
else:
    print("ℹ️ Không tìm thấy thêm đơn hủy qua endpoint waybillNo.")

print("🏁 Hoàn tất quét JFS.")
