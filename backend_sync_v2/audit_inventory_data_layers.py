import psycopg2
import pandas as pd
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Auditing Inventory Data Layer 1 (PostgreSQL & JSON Files)...")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# 1. Check PostgreSQL tables related to inventory
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%inventory%' OR table_name LIKE '%rack%' OR table_name LIKE '%chute%';")
tables = cur.fetchall()
print("PostgreSQL Inventory Tables:", tables)

# Check enriched tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'enriched';")
enriched_tables = [r[0] for r in cur.fetchall()]
print("Enriched Schema Tables:", enriched_tables)

# Sample dispatch_enriched for inventory/rack fields
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'dispatch_enriched' AND (column_name LIKE '%zone%' OR column_name LIKE '%area%' OR column_name LIKE '%capacity%');")
inv_cols = [r[0] for r in cur.fetchall()]
print("Inventory/Zone columns in dispatch_enriched:", inv_cols)

conn.close()

# 2. Check local JSON files
json_files = ['data/inventory.json', 'data/last_update.json', 'data/live/inbound_kpi_summary.json']
for jf in json_files:
    if os.path.exists(jf):
        sz = os.path.getsize(jf)
        print(f"File {jf} exists: size = {sz} bytes")
    else:
        print(f"File {jf} DOES NOT EXIST!")
