import psycopg2, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db', user='postgres',
    password='Tien@giang0203', host='127.0.0.1', port=5433
)
cur = conn.cursor()

SEP = "=" * 65
print(SEP)
print("  XÁC NHẬN CHÍNH XÁC: 18.308 ĐƠN TRÊN LAYOUT ĐÃ CÓ OUTBOUND TIME CHƯA?")
print(SEP)

cur.execute("""
    SELECT
        status_sys,
        COUNT(*) AS total_cnt,
        COUNT(inbound_scandate) AS inbound_cnt,
        COUNT(outbound_scandate) AS outbound_cnt
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created >= '2026-08-10'
    GROUP BY status_sys
    ORDER BY total_cnt DESC
""")
rows = cur.fetchall()
print(f"{'TRẠNG THÁI (status_sys)':<25} {'SỐ LƯỢNG ĐƠN':>15} {'INBOUND TIME':>15} {'OUTBOUND TIME':>15}")
print("-" * 72)
for r in rows:
    st = str(r[0])
    cnt = r[1]
    in_c = r[2]
    out_c = r[3]
    print(f"{st:<25} {cnt:>15,} {in_c:>15,} {out_c:>15,}")

print(SEP)

cur.execute("""
    SELECT
        COUNT(*) AS total_without_outbound,
        COUNT(CASE WHEN outbound_scandate IS NOT NULL THEN 1 END) AS total_with_outbound
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created >= '2026-08-10'
""")
res = cur.fetchone()
print(f"  - Tổng số đơn chưa có Outbound Time trong tập Layout  : {res[0]:,} đơn")
print(f"  - Số đơn có Outbound Time trong tập này               : {res[1]:,} đơn (HOÀN TOÀN KHÔNG CÓ)")

print(SEP)
cur.close()
conn.close()
