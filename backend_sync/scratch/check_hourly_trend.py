import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(
    dbname='logistics_db',
    user='postgres',
    password='Tien@giang0203',
    host='127.0.0.1',
    port=5433
)
cur = conn.cursor()

EXCLUDE_NORTH = """
    AND NOT (
        COALESCE(pickup_station, '') LIKE 'BN HUB%%' OR
        COALESCE(pickup_station, '') LIKE 'HN %%' OR
        COALESCE(pickup_station, '') LIKE 'HD %%' OR
        COALESCE(pickup_station, '') LIKE 'HY %%' OR
        COALESCE(rank, '') = 'BN HUB'
    )
"""

print("=================================================================")
print("  HOURLY INBOUND BREAKDOWN BY OPERATING DATE AND HOUR")
print("=================================================================")

for d in ['2026-08-08', '2026-08-09', '2026-08-10', '2026-08-11']:
    cur.execute("""
        SELECT 
            TO_CHAR(inbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:00') as hr,
            COUNT(*) 
        FROM enriched.dispatch_enriched
        WHERE inbound_scandate IS NOT NULL
    """ + EXCLUDE_NORTH + """
          AND (CASE WHEN EXTRACT(HOUR FROM inbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6 
                    THEN (inbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                    ELSE (inbound_scandate AT TIME ZONE 'Asia/Ho_Chi_Minh')::date END)::text = %s
        GROUP BY hr
        ORDER BY hr;
    """, (d,))
    rows = cur.fetchall()
    print(f"\n--- Operating Date: {d} ---")
    print(dict(rows))

print("\n=================================================================")
print("  HOURLY CREATED BREAKDOWN BY OPERATING DATE AND HOUR")
print("=================================================================")

for d in ['2026-08-08', '2026-08-09', '2026-08-10', '2026-08-11']:
    cur.execute("""
        SELECT 
            TO_CHAR(created_time AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:00') as hr,
            COUNT(*) 
        FROM enriched.dispatch_enriched
        WHERE created_time IS NOT NULL
    """ + EXCLUDE_NORTH + """
          AND (CASE WHEN EXTRACT(HOUR FROM created_time AT TIME ZONE 'Asia/Ho_Chi_Minh') < 6 
                    THEN (created_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date - 1
                    ELSE (created_time AT TIME ZONE 'Asia/Ho_Chi_Minh')::date END)::text = %s
        GROUP BY hr
        ORDER BY hr;
    """, (d,))
    rows = cur.fetchall()
    print(f"\n--- Operating Date: {d} ---")
    print(dict(rows))

cur.close()
conn.close()
