"""
backfill_inbound_weight.py  (v2 - PostgreSQL)
──────────────────────────────────────────────────────────────────────────────
Script backfill: lấy lại weight từ Inbound Scan API cho các đơn trong
PostgreSQL DB đang có weight = 0.0, rồi cập nhật lại DB và regenerate JSON.

Chạy thủ công 1 lần sau khi fix bug sync_to_sheets.py:
    python backend_sync/backfill_inbound_weight.py
"""

import sys, os, json
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

# Import helper từ sync_to_sheets
from sync_to_sheets import (
    build_session, TokenManager, pull_scan,
    ACCOUNT, PASSWORD, COUNTRY_ID, URL_SCAN,
    DB_CONN_PARAMS
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG   = os.path.join(BASE_DIR, 'config')

# ─── 1. Đọc headers / payload template ───────────────────────────────────────
with open(os.path.join(CONFIG, 'inboundheaders.json'), encoding='utf-8') as f:
    IB_HEADERS = json.load(f)
with open(os.path.join(CONFIG, 'inboundpayload.json'), encoding='utf-8') as f:
    IB_PAYLOAD = json.load(f)

# ─── 2. Build session + token ─────────────────────────────────────────────────
session   = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)

# ─── 3. Tìm những ngày có đơn weight = 0 trong PostgreSQL ────────────────────
print(f"🔗 Kết nối PostgreSQL: {DB_CONN_PARAMS['host']}:{DB_CONN_PARAMS['port']}")
conn = psycopg2.connect(**DB_CONN_PARAMS)
cur  = conn.cursor()

cur.execute("""
    SELECT DISTINCT LEFT(inbound_scandate::text, 10) AS op_date
    FROM shipments
    WHERE inbound_scandate IS NOT NULL
      AND inbound_scandate::text != ''
      AND weight = 0.0
    ORDER BY op_date DESC
""")
dates_with_zero = [r[0] for r in cur.fetchall() if r[0]]

cur.execute("SELECT COUNT(*) FROM shipments WHERE weight = 0.0")
total_zero = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM shipments")
total_all  = cur.fetchone()[0]
conn.close()

print(f"📊 Tổng đơn: {total_all:,} | Đơn weight=0: {total_zero:,} ({total_zero/total_all*100:.1f}%)")
print(f"📋 Tìm thấy {len(dates_with_zero)} ngày có đơn weight=0: {dates_with_zero}\n")

# ─── 4. Với mỗi ngày, gọi Inbound API lấy weight ─────────────────────────────
weight_map: dict[str, float] = {}  # waybillNo → weight

for date_str in dates_with_zero:
    print(f"🔄 Đang pull Inbound weight cho ngày {date_str}...")
    payload = {
        **IB_PAYLOAD,
        'beginDate': f'{date_str} 00:00:00',
        'endDate':   f'{date_str} 23:59:59',
        'current': 1,
        'size': 1000,
    }
    try:
        records = pull_scan(
            session, token_mgr,
            URL_SCAN, IB_HEADERS, {},
            payload, label=f'Backfill {date_str}'
        )
        count = 0
        for r in records:
            wb = str(r.get('billNo') or r.get('waybillNo') or '').strip()
            if not wb:
                continue
            try:
                wt = float(r.get('weight') or r.get('settlementWeight') or r.get('bulkWeight') or 0.0)
            except (ValueError, TypeError):
                wt = 0.0
            if wt > 0 and (wb not in weight_map or weight_map[wb] == 0.0):
                weight_map[wb] = wt
                count += 1
        print(f"   ✅ Lấy được {len(records)} bản ghi, {count} mã có weight > 0 mới")
    except Exception as e:
        print(f"   ❌ Lỗi ngày {date_str}: {e}")

# ─── 5. Cập nhật PostgreSQL ───────────────────────────────────────────────────
if not weight_map:
    print("\n⚠️  Không có weight nào cần cập nhật.")
else:
    print(f"\n💾 Cập nhật {len(weight_map):,} waybill vào PostgreSQL...")
    conn = psycopg2.connect(**DB_CONN_PARAMS)
    cur  = conn.cursor()

    # Batch update: chỉ update đơn đang weight=0
    BATCH = 500
    waybills = list(weight_map.items())
    updated  = 0

    for i in range(0, len(waybills), BATCH):
        batch = waybills[i:i+BATCH]
        # Dùng VALUES temp table để update hiệu quả
        args = [(wt, wb) for wb, wt in batch]
        cur.executemany(
            "UPDATE shipments SET weight = %s WHERE waybillno = %s AND weight = 0.0",
            args
        )
        updated += cur.rowcount
        if (i // BATCH) % 20 == 0:
            print(f"   ... {i + len(batch):,}/{len(waybills):,} ({updated:,} updated)")

    conn.commit()
    conn.close()
    print(f"   ✅ Đã cập nhật {updated:,} bản ghi trong PostgreSQL.")

    # Kiểm tra lại sau backfill
    conn = psycopg2.connect(**DB_CONN_PARAMS)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM shipments WHERE weight = 0.0")
    remaining_zero = cur.fetchone()[0]
    cur.execute("SELECT AVG(weight) FROM shipments WHERE weight > 0")
    avg_wt = cur.fetchone()[0]
    conn.close()
    print(f"\n📊 Sau backfill: Còn {remaining_zero:,} đơn weight=0 | Avg weight (>0): {avg_wt:.2f} kg")

print("""
╔══════════════════════════════════════════════════════════════╗
║  Backfill xong! Để cập nhật file JSON cho frontend, chạy:   ║
║      python backend_sync/sync_to_sheets.py                   ║
║  Hoặc đợi scheduled task chạy tự động (~30 phút).           ║
╚══════════════════════════════════════════════════════════════╝
""")
