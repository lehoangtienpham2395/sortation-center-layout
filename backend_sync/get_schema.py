import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('backend_sync/db/state.db')
c = conn.cursor()
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='shipments'")
schema = c.fetchone()[0]
print(schema)
print("\n--- COLUMN INFO ---")
c.execute("PRAGMA table_info(shipments)")
for row in c.fetchall():
    print(row)
conn.close()
