import sqlite3, sys, pandas as pd
from datetime import datetime, timedelta
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend_sync/db/state.db')

# Lấy TẤT CẢ đơn Forecast (cả active lẫn inactive) với ngày điều phối
df = pd.read_sql_query("""
    SELECT 
        waybillNo, status_order, is_active,
        dispatchNetworkTime, Pickup_time,
        inbound_scanDate, outbound_scanDate,
        time_ref, last_updated
    FROM shipments
    WHERE data_source = 'Forecast'
""", conn)
conn.close()

# Tính ngày vận hành Forecast (giống logic trong sync script)
def get_op_date(dt_str):
    if not dt_str or str(dt_str).strip() in ('', 'nan', 'None'):
        return ''
    try:
        dt = pd.to_datetime(dt_str)
        if dt.hour < 6:
            return (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except:
        return ''

df['ngay_fc'] = df['dispatchNetworkTime'].apply(get_op_date)
df['ngay_pickup'] = df['Pickup_time'].apply(get_op_date)

# Ngày vận hành hôm nay và hôm qua
today = '2026-07-13'
yesterday = '2026-07-12'

# Breakdown theo ngày vận hành + is_active
print("=== BREAKDOWN THEO NGÀY VẬN HÀNH FORECAST ===")
breakdown = df.groupby(['ngay_fc', 'is_active']).size().reset_index(name='count')
print(breakdown[breakdown['ngay_fc'] >= '2026-07-10'].to_string(index=False))

print(f"\n=== TẬP TRUNG VÀO '{yesterday}' (Rớt hôm trước) ===")
df_yday = df[df['ngay_fc'] == yesterday]
print(f"Tổng đơn ngày {yesterday}: {len(df_yday):,}")
print(f"  is_active=1 (còn active): {df_yday['is_active'].eq(1).sum():,}")
print(f"  is_active=0 (đã tắt):    {df_yday['is_active'].eq(0).sum():,}")
print(f"\nBreakdown status:")
print(df_yday.groupby(['is_active', 'status_order']).size().reset_index(name='count').to_string(index=False))

print(f"\n=== TẬP TRUNG VÀO '{today}' (Rớt hôm nay) ===")
df_today = df[df['ngay_fc'] == today]
print(f"Tổng đơn ngày {today}: {len(df_today):,}")
print(f"  is_active=1 (còn active): {df_today['is_active'].eq(1).sum():,}")
print(f"  is_active=0 (đã tắt):    {df_today['is_active'].eq(0).sum():,}")

# Kết luận 3488 đơn
print(f"\n=== KẾT LUẬN 3.488 ĐƠN THIẾU ===")
missing = 19664 - df[df['is_active']==1].shape[0]
in_db_inactive = df[(df['ngay_fc'] == yesterday) & (df['is_active'] == 0)]
not_in_db = 3488 - len(in_db_inactive)
print(f"Rớt hôm qua ({yesterday}) trong DB (inactive): {len(in_db_inactive):,}")
print(f"Rớt hôm qua ({yesterday}) trong DB (active):   {df_yday['is_active'].eq(1).sum():,}")
print(f"→ {len(in_db_inactive):,} đơn CÓ trong DB nhưng bị tắt (is_active=0)")
print(f"→ Còn lại ~{max(0, 3488 - len(df_yday)):,} đơn CHƯA có trong DB (chưa kéo về)")
