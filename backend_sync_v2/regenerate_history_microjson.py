import os
import sys
import json
import psycopg2

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = [
    os.path.join(BASE_DIR, "data"),
    os.path.join(BASE_DIR, "public", "data"),
    os.path.join(BASE_DIR, "src", "data"),
]

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# ============================================================
# NGUỒN SỰ THẬT: DB daily_kpi_snapshot (flag-based, user xác nhận ĐÚNG).
# Tái tạo history micro-JSON theo đúng giá trị snapshot đã chốt trong DB.
# ============================================================
cur.execute("""
    SELECT op_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong
    FROM enriched.daily_kpi_snapshot
    WHERE op_date BETWEEN '2026-07-27' AND '2026-08-01'
    ORDER BY op_date;
""")
rows = cur.fetchall()

print("=== Tái tạo history micro-JSON từ daily_kpi_snapshot (flag-based ĐÚNG) ===")
for op_date, rht, rhn, rtd in rows:
    d = op_date.strftime('%Y-%m-%d')
    rot_hom_truoc = int(rht or 0)
    rot_hom_nay = int(rhn or 0)
    rot_ton_dong = int(rtd or 0)
    forecast_total = rot_hom_truoc + rot_hom_nay

    for root in ROOTS:
        hist_dir = os.path.join(root, "history", d)
        os.makedirs(hist_dir, exist_ok=True)
        kpi_path = os.path.join(hist_dir, "inbound_kpi_summary.json")

        # Giữ các trường inbound/weight từ file cũ nếu có, chỉ sửa rot KPI.
        existing = {}
        if os.path.exists(kpi_path):
            try:
                with open(kpi_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        kpi = {
            "op_date": d,
            "contract_version": "2.0.0",
            "inbound_orders": existing.get("inbound_orders", 0),
            "inbound_weight_ton": existing.get("inbound_weight_ton", 0.0),
            "forecast_total": forecast_total,
            "rot_hom_truoc": rot_hom_truoc,
            "rot_hom_nay": rot_hom_nay,
            "rot_ton_dong": rot_ton_dong,
            "linehaul_bn_hub": existing.get("linehaul_bn_hub", 0),
        }
        with open(kpi_path, 'w', encoding='utf-8') as f:
            json.dump(kpi, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {d}: truoc={rot_hom_truoc} nay={rot_hom_nay} ton={rot_ton_dong} forecast={forecast_total}")

conn.close()
print("\nĐã tái tạo history micro-JSON từ DB cho cả 3 thư mục (data, public/data, src/data).")
