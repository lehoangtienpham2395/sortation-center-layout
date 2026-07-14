"""
backfill_inbound_weight.py
──────────────────────────────────────────────────────────────────────────────
Script backfill: lấy lại weight từ Inbound Scan API cho các đơn trong DB
đang có weight = 0.0, rồi cập nhật lại DB và regenerate JSON.

Chạy thủ công 1 lần sau khi fix bug sync_to_sheets.py:
    python backend_sync/backfill_inbound_weight.py
"""

import sys, os, json, sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

# Import helper từ sync_to_sheets
from sync_to_sheets import (
    build_session, TokenManager, auth_post, pull_scan,
    LOGIN_URL, ACCOUNT, PASSWORD, COUNTRY_ID, URL_SCAN
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'db', 'state.db')
CONFIG   = os.path.join(BASE_DIR, 'config')

# ─── 1. Đọc headers / payload template ───────────────────────────────────────
with open(os.path.join(CONFIG, 'inboundheaders.json'), encoding='utf-8') as f:
    IB_HEADERS = json.load(f)
with open(os.path.join(CONFIG, 'inboundpayload.json'), encoding='utf-8') as f:
    IB_PAYLOAD = json.load(f)

# ─── 2. Build session + token ─────────────────────────────────────────────────
session   = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)

# ─── 3. Tìm những ngày có đơn weight = 0 trong DB ────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()

cur.execute("""
    SELECT DISTINCT SUBSTR(inbound_scanDate, 1, 10) AS op_date
    FROM shipments
    WHERE inbound_scanDate IS NOT NULL
      AND inbound_scanDate != ''
      AND weight = 0.0
    ORDER BY op_date DESC
""")
dates_with_zero = [r['op_date'] for r in cur.fetchall() if r['op_date']]
conn.close()

print(f"📋 Tìm thấy {len(dates_with_zero)} ngày có đơn weight=0: {dates_with_zero}")

# ─── 4. Với mỗi ngày, gọi Inbound API lấy weight ─────────────────────────────
weight_map: dict[str, float] = {}  # waybillNo → weight

for date_str in dates_with_zero:
    print(f"\n🔄 Đang pull Inbound weight cho ngày {date_str}...")
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
        print(f"   ❌ Lỗi: {e}")

# ─── 5. Cập nhật DB ──────────────────────────────────────────────────────────
if not weight_map:
    print("\n⚠️  Không có weight nào cần cập nhật.")
else:
    print(f"\n💾 Cập nhật {len(weight_map)} waybill vào DB...")
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    updated = 0
    for wb, wt in weight_map.items():
        cur.execute("""
            UPDATE shipments
            SET weight = ?
            WHERE waybillNo = ? AND weight = 0.0
        """, (wt, wb))
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f"   ✅ Đã cập nhật {updated} bản ghi.")

# ─── 6. Nhắc chạy lại sync để regenerate JSON ────────────────────────────────
print("""
╔══════════════════════════════════════════════════════════════╗
║  Backfill xong! Để cập nhật file JSON cho frontend, chạy:   ║
║      python backend_sync/sync_to_sheets.py                   ║
║  Hoặc đợi scheduled task chạy tự động (~30 phút).           ║
╚══════════════════════════════════════════════════════════════╝
""")
