import sys; sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn()
cur = conn.cursor()

cur.execute("""
    SELECT
        COUNT(*) as total_tao_hom_nay,
        SUM(CASE WHEN status_sys = 'Đã lấy hàng' THEN 1 ELSE 0 END) as da_lay_hang,
        SUM(CASE WHEN status_sys = 'Đã điều phối nhân viên' THEN 1 ELSE 0 END) as da_dieu_phoi_nv,
        SUM(CASE WHEN status_sys = 'Lấy hàng thất bại' THEN 1 ELSE 0 END) as lay_hang_that_bai,
        SUM(CASE WHEN status_sys = 'Đã điều phối bưu cục' THEN 1 ELSE 0 END) as da_dieu_phoi_bc,
        SUM(CASE WHEN status_sys = 'Đã hủy' THEN 1 ELSE 0 END) as da_huy
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-07-28 06:00:00+07';
""")
r = cur.fetchone()
print(f"1. Tổng số đơn TẠO TỪ 06:00 SÁNG NAY (khớp 6,733 trên màn hình JFS): {r[0]:,}")
print(f"   ├── Đã lấy hàng (Pickup Done — CHÍNH LA RỚT HÔM NAY):             {r[1]:,}")
print(f"   ├── Đã điều phối nhân viên (Chưa lấy hàng):                       {r[2]:,}")
print(f"   ├── Lấy hàng thất bại (Chưa lấy hàng):                             {r[3]:,}")
print(f"   ├── Đã điều phối bưu cục (Mới tạo, chưa điều phối NV):             {r[4]:,}")
print(f"   └── Đã hủy:                                                       {r[5]:,}")

conn.close()
