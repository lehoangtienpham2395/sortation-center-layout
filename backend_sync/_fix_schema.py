import psycopg2, sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
    except Exception: pass

conn = psycopg2.connect(
    host='127.0.0.1', port=5433, dbname='logistics_db',
    user='postgres', password='Tien@giang0203', connect_timeout=5
)
cur = conn.cursor()

# Fix 1: Set DEFAULT for data_source (so any NULL insert gets replaced)
try:
    cur.execute("ALTER TABLE enriched.dispatch_enriched ALTER COLUMN data_source SET DEFAULT 'pipeline_v6';")
    print("✅ data_source DEFAULT set to 'pipeline_v6'")
except Exception as e:
    print(f"⚠️  data_source default: {e}")
    conn.rollback()

# Fix 2: Add is_transit column if not exists
try:
    cur.execute("""
        ALTER TABLE enriched.dispatch_enriched 
        ADD COLUMN IF NOT EXISTS is_transit SMALLINT DEFAULT 0;
    """)
    print("✅ is_transit column ensured")
except Exception as e:
    print(f"⚠️  is_transit: {e}")
    conn.rollback()

# Fix 3: Patch any existing NULL data_source rows
try:
    cur.execute("""
        UPDATE enriched.dispatch_enriched 
        SET data_source = 'pipeline_v6' 
        WHERE data_source IS NULL;
    """)
    rows = cur.rowcount
    print(f"✅ Patched {rows} rows with NULL data_source")
except Exception as e:
    print(f"⚠️  patch null: {e}")
    conn.rollback()

conn.commit()
conn.close()
print("Done.")
