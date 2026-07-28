import sys; sys.path.insert(0, 'backend_sync')
from sync_postgre import get_pg_conn

conn = get_pg_conn()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE operation_date_created = '2026-07-28'")
cnt_created_today = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM enriched.dispatch_enriched WHERE created_time >= '2026-07-28 06:00:00+07'")
cnt_created_6am = cur.fetchone()[0]

print('=== BREAKDOWN FOR CREATED TODAY >= 06:00 AM ===')
print(f'Total created >= 06:00 AM today: {cnt_created_6am:,}')
print(f'Total created today (all hours): {cnt_created_today:,}')

cur.execute("""
    SELECT status_sys, flag_pickup, flag_arrival, flag_inbound, flag_outbound, COUNT(*)
    FROM enriched.dispatch_enriched
    WHERE created_time >= '2026-07-28 06:00:00+07'
    GROUP BY status_sys, flag_pickup, flag_arrival, flag_inbound, flag_outbound
    ORDER BY COUNT(*) DESC
""")
rows = cur.fetchall()
print()
print(f"{'status_sys':<25} {'flag_pk':<8} {'flag_arr':<9} {'flag_inb':<9} {'flag_out':<9} {'count':>8}")
print('-'*70)
for r in rows:
    print(f"{str(r[0]):<25} {r[1]:<8} {r[2]:<9} {r[3]:<9} {r[4]:<9} {r[5]:>8,}")

conn.close()
