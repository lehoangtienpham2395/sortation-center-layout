import psycopg2, sys
sys.stdout.reconfigure(encoding='utf-8')
try:
    conn = psycopg2.connect(
        host='127.0.0.1', port=5433, dbname='logistics_db',
        user='postgres', password='Tien@giang0203', connect_timeout=5
    )
    cur = conn.cursor()

    # Check constraints on dispatch_enriched
    cur.execute("""
        SELECT conname, contype, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'enriched.dispatch_enriched'::regclass
        ORDER BY contype
    """)
    rows = cur.fetchall()
    print(f'Constraints on dispatch_enriched ({len(rows)}):')
    for name, ctype, defn in rows:
        t = {'p':'PRIMARY KEY','u':'UNIQUE','c':'CHECK','f':'FOREIGN KEY'}.get(ctype, ctype)
        print(f'  [{t}] {name}: {defn}')

    # Check duplicate tracking values in current table
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT tracking) FROM enriched.dispatch_enriched")
    total, distinct = cur.fetchone()
    print(f'\nCurrent rows: {total:,} | Distinct tracking: {distinct:,} | Dupes: {total-distinct:,}')

    conn.close()
except Exception as e:
    print('ERROR:', e)
