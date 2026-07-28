import sys; sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn(); cur = conn.cursor()
cur.execute('SELECT op_date, total_inbound, total_outbound, total_pickup, total_created, rot_hom_truoc, rot_hom_nay, total_backlog, outbound_rate FROM reporting.kpi_daily ORDER BY op_date DESC LIMIT 7;')
rows = cur.fetchall()

print('=== KPI DAILY SAU KHI CẬP NHẬT ĐÚNG TIÊU CHÍ RỚT HÔM NAY ===\n')
print(f"{'op_date':<12} {'inbound':>8} {'outbound':>9} {'created':>8} {'rot_T':>6} {'rot_H':>8} {'backlog':>8}")
print('-'*65)
for r in rows:
    print(f"{str(r[0]):<12} {r[1]:>8,} {r[2]:>9,} {r[4]:>8,} {r[5]:>6,} {r[6]:>8,} {r[7]:>8,}")
conn.close()
