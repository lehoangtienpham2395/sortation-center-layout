import os
import json
import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PUBLIC_DATA_DIR = os.path.join(BASE_DIR, "public", "data")

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Get list of unique operating dates in DB
cur.execute('''
    SELECT DISTINCT COALESCE(op_date_pickup::date, operation_date_created::date)::text
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::date, operation_date_created::date) IS NOT NULL
    ORDER BY 1 DESC;
''')

dates = [r[0] for r in cur.fetchall()]
print("Operating dates found in DB:", dates)

for d_str in dates:
    # KPI lấy từ daily_kpi_snapshot (flag-based = chuẩn), KHÔNG tính status-based.
    cur.execute('''
        SELECT rot_hom_truoc, rot_hom_nay, rot_ton_dong
        FROM enriched.daily_kpi_snapshot
        WHERE op_date = %s::date;
    ''', (d_str,))
    snap = cur.fetchone()
    if snap:
        rot_truoc = int(snap[0])
        rot_nay = int(snap[1])
        rot_ton = int(snap[2])
    else:
        # Không có snapshot flag-based cho ngày này → không được ghi đè/zero hoá.
        # Bỏ qua ghi inbound_kpi_summary.json (giữ nguyên file cũ), vẫn cập nhật
        # inbound_orders_status.json nếu có dữ liệu status.
        print(f"   ⏭  SKIP kpi_summary {d_str}: không có daily_kpi_snapshot (giữ file cũ)")
        rot_truoc, rot_nay, rot_ton = None, None, None

    # Query summary metrics for date d_str
    cur.execute('''
        SELECT 
            SUM(CASE WHEN status_sys = 'Inbound' THEN 1 ELSE 0 END) as inbound_cnt,
            SUM(CASE WHEN status_sys = 'Transporting' THEN 1 ELSE 0 END) as transp_cnt,
            SUM(CASE WHEN status_sys = 'Pickup Done' THEN 1 ELSE 0 END) as pickup_cnt,
            SUM(CASE WHEN status_sys = 'Created' THEN 1 ELSE 0 END) as created_cnt,
            SUM(CASE WHEN status_sys = 'Inbound' THEN orders_weight ELSE 0 END) / 1000.0 as inb_wt,
            SUM(CASE WHEN status_sys = 'Transporting' THEN orders_weight ELSE 0 END) / 1000.0 as transp_wt,
            SUM(CASE WHEN status_sys = 'Pickup Done' THEN orders_weight ELSE 0 END) / 1000.0 as pickup_wt,
            SUM(CASE WHEN status_sys = 'Created' THEN orders_weight ELSE 0 END) / 1000.0 as created_wt
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) = %s::date;
    ''', (d_str,))
    
    row = cur.fetchone()
    inb_c, tr_c, pk_c, cr_c, inb_w, tr_w, pk_w, cr_w = row
    inb_c = int(inb_c or 0)
    tr_c = int(tr_c or 0)
    pk_c = int(pk_c or 0)
    cr_c = int(cr_c or 0)
    
    inb_w = round(float(inb_w or 0), 3)
    tr_w = round(float(tr_w or 0), 3)
    pk_w = round(float(pk_w or 0), 3)
    cr_w = round(float(cr_w or 0), 3)
    
    kpi_summary = None
    if rot_truoc is not None:
        kpi_summary = {
            "op_date": d_str,
            "contract_version": "2.0.0",
            "inbound_orders": inb_c,
            "inbound_weight_ton": inb_w,
            "forecast_total": rot_truoc + rot_nay,
            "rot_hom_truoc": rot_truoc,
            "rot_hom_nay": rot_nay,
            "rot_ton_dong": rot_ton,
            "linehaul_bn_hub": 0
        }
    
    orders_status = {
        "op_date": d_str,
        "contract_version": "2.0.0",
        "inbound": inb_c,
        "transporting": tr_c,
        "pickup_done": pk_c,
        "created": cr_c,
        "total": inb_c + tr_c + pk_c + cr_c,
        "inbound_weight": inb_w,
        "transporting_weight": tr_w,
        "pickup_done_weight": pk_w,
        "created_weight": cr_w
    }
    
    # Write to data/history/<date>/ and public/data/history/<date>/
    for root in [DATA_DIR, PUBLIC_DATA_DIR]:
        h_dir = os.path.join(root, "history", d_str)
        os.makedirs(h_dir, exist_ok=True)
        if kpi_summary is not None:
            with open(os.path.join(h_dir, "inbound_kpi_summary.json"), "w", encoding="utf-8") as f:
                json.dump(kpi_summary, f, ensure_ascii=False, indent=2)
        with open(os.path.join(h_dir, "inbound_orders_status.json"), "w", encoding="utf-8") as f:
            json.dump(orders_status, f, ensure_ascii=False, indent=2)

print("Generated all history micro-JSON files successfully!")
conn.close()
