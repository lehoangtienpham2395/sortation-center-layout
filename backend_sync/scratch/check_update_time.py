import psycopg2, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db', user='postgres',
    password='Tien@giang0203', host='127.0.0.1', port=5433
)
cur = conn.cursor()

# 1. Xem cột nào liên quan đến thời gian update row trong DB
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'enriched'
      AND table_name = 'dispatch_enriched'
      AND (column_name ILIKE '%updat%' OR column_name ILIKE '%creat%')
    ORDER BY column_name
""")
print("=== COLUMNS THỜI GIAN CẬP NHẬT ===")
cols = cur.fetchall()
for r in cols:
    print(f"  {r[0]:<35} {r[1]}")

# 2. Phân bố theo giờ: khi nào DB được cập nhật gần nhất (last_updated)
print("\n=== PHÂN BỐ CẬP NHẬT ĐƠN HÀNG THEO GIỜ (2 ngày gần nhất) ===")
cur.execute("""
    SELECT
        TO_CHAR(last_updated AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:00') AS hour_slot,
        COUNT(*) AS rows_updated
    FROM enriched.dispatch_enriched
    WHERE last_updated >= NOW() - INTERVAL '2 days'
    GROUP BY 1
    ORDER BY 1
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        bar = '#' * (r[1] // 200)
        print(f"  {r[0]}  |  {r[1]:>6,}  {bar}")
else:
    # Thử với created_at nếu không có last_updated
    print("  (Không có cột last_updated — thử created_at)")
    cur.execute("""
        SELECT
            TO_CHAR(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:00') AS hour_slot,
            COUNT(*) AS rows_updated
        FROM enriched.dispatch_enriched
        WHERE created_at >= NOW() - INTERVAL '2 days'
        GROUP BY 1
        ORDER BY 1
    """)
    rows2 = cur.fetchall()
    for r in rows2:
        bar = '#' * (r[1] // 200)
        print(f"  {r[0]}  |  {r[1]:>6,}  {bar}")

cur.close()
conn.close()
