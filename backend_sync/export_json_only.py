import os, sys, psycopg2
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

from sync_to_sheets import (
    DB_CONN_PARAMS, get_db_conn, update_inbound_sheets, get_operating_date,
    load_valid, VALID_FILE
)

print("🚀 Exporting JSON files directly from PostgreSQL (without JFS API call)...")

_, d_buucuc, _, _ = load_valid(VALID_FILE)

# 1. Export Inbound aggregated sheet (inbound.json, arrival.json, etc.)
# We pass ss=None so it only writes local JSONs (data/inbound.json, data/arrival.json, etc.)
# and doesn't push to Google Sheets.
update_inbound_sheets(None, {}, {}, d_buucuc)

# 2. Export latest.json.gz directly from PostgreSQL shipments table
print("\n📦 Exporting latest.json.gz directly from PostgreSQL shipments table...")
conn = get_db_conn()
df_latest = pd.read_sql_query("""
    SELECT waybillno AS "waybillNo", data_source, weight, picknetworkname AS "pickNetworkName",
           dispatch_plan, pickup_time AS "Pickup_time", pickup_label, pickup_ontime AS "Pickup_ontime",
           dispatchnetworktime AS "dispatchNetworkTime", next_station, tuyen AS "Tuyến", rank AS "Rank",
           inbound_network, inbound_scandate AS "inbound_scanDate", outbound_scandate AS "outbound_scanDate",
           arrival_time AS "Arrival_time", dispatch_actual, status_order, time_ref, is_backlog, is_active
    FROM shipments
""", conn)
conn.close()

if not df_latest.empty:
    os.makedirs("data", exist_ok=True)
    df_latest.to_json("data/latest.json.gz", orient="records", force_ascii=False, compression="gzip")
    print(f"   💾 Đã lưu file 'data/latest.json.gz' với {len(df_latest):,} dòng.")

# 3. Copy data/*.json and data/*.json.gz to src/data/
print("\n📋 Copying generated JSONs to src/data/ for frontend...")
import shutil
os.makedirs("src/data", exist_ok=True)
for fn in os.listdir("data"):
    if fn.endswith(".json") or fn.endswith(".json.gz"):
        shutil.copy2(os.path.join("data", fn), os.path.join("src/data", fn))
        print(f"   Copied {fn} -> src/data/{fn}")

print("\n✅ Export and Copy Completed Successfully!")
