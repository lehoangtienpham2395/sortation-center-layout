import sys; sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn(); cur = conn.cursor()

cur.execute("""
    SELECT
        COUNT(*) as total_created_today,
        SUM(CASE WHEN flag_inbound=1 OR flag_arrival=1 THEN 1 ELSE 0 END) as da_ve_hub,
        SUM(CASE WHEN status_sys = 'Đã hủy' THEN 1 ELSE 0 END) as da_huy
    FROM enriched.dispatch_enriched
    WHERE operation_date_created = '2026-07-28';
""")
r = cur.fetchone()
print(f"Tổng số đơn tạo ca hôm nay (2026-07-28): {r[0]:,}")
print(f"  ├── Đã Arrival / Inbound về HUB:      {r[1]:,}")
print(f"  ├── Đã Hủy:                             {r[2]:,}")
print(f"  └── RỚT HÔM NAY (chưa về HUB, trừ Hủy): {r[0] - r[1] - r[2]:,}")

conn.close()
