import psycopg2, os
conn = psycopg2.connect(
    host='127.0.0.1', port=5433, dbname='logistics_db',
    user='postgres', password='Tien@giang0203', connect_timeout=5
)
cur = conn.cursor()
cur.execute("""
    SELECT column_name, ordinal_position, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema='enriched' AND table_name='dispatch_enriched'
    ORDER BY ordinal_position
""")
rows = cur.fetchall()
print(f"Total columns: {len(rows)}")
for r in rows:
    print(f"  {r[1]:2d}. {r[0]:<30s} {r[2]:<20s} nullable={r[3]}  default={r[4]}")
conn.close()
