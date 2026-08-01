import psycopg2
import json
import sys
import os
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

dates = ['2026-07-27', '2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31', '2026-08-01']

results = {}

for target_date in dates:
    prev_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    
    cur.execute('''
        SELECT 
            COALESCE(op_date_pickup::text, operation_date_created::text) AS ref_date,
            flag_inbound,
            flag_outbound,
            status_sys
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= %s::date;
    ''', (target_date,))
    
    rows = cur.fetchall()
    
    rot_hom_truoc = 0
    rot_hom_nay = 0
    rot_ton_dong = 0
    
    for ref_d, has_in, has_out, status_sys in rows:
        stn = str(status_sys or '').strip()
        is_canceled = (stn == 'Đã hủy')
        is_rot = (not has_in) and (not has_out) and (not is_canceled)
        
        if is_rot and ref_d:
            ref_d_str = str(ref_d)[:10]
            if ref_d_str == target_date:
                rot_hom_nay += 1
            elif ref_d_str == prev_date:
                rot_hom_truoc += 1
            elif ref_d_str < prev_date:
                rot_ton_dong += 1
                
    fc_total = rot_hom_truoc + rot_hom_nay
    results[target_date] = {
        'rot_hom_truoc': rot_hom_truoc,
        'rot_hom_nay': rot_hom_nay,
        'rot_ton_dong': rot_ton_dong,
        'forecast_total': fc_total
    }
    
    cur.execute('''
        INSERT INTO enriched.daily_kpi_snapshot (op_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (op_date) DO UPDATE SET
            rot_hom_truoc = EXCLUDED.rot_hom_truoc,
            rot_hom_nay   = EXCLUDED.rot_hom_nay,
            rot_ton_dong  = EXCLUDED.rot_ton_dong,
            updated_at    = CURRENT_TIMESTAMP;
    ''', (target_date, rot_hom_truoc, rot_hom_nay, rot_ton_dong))

conn.commit()

# Also update last_update.json and history folders for all dates
BASE_DIR = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"

# Read existing last_update.json
last_update_path = os.path.join(BASE_DIR, "public", "data", "last_update.json")
if os.path.exists(last_update_path):
    with open(last_update_path, 'r', encoding='utf-8') as f:
        lu_data = json.load(f)
else:
    lu_data = {}

daily_snaps = lu_data.get("daily_snapshots", {})

for d in dates:
    r = results[d]
    daily_snaps[d] = {
        "rot_hom_truoc": r['rot_hom_truoc'],
        "rot_hom_nay": r['rot_hom_nay'],
        "rot_ton_dong": r['rot_ton_dong'],
        "is_frozen": (d < '2026-08-01')
    }
    
    # Save to public/data/history/<d>/inbound_kpi_summary.json
    hist_dir = os.path.join(BASE_DIR, "public", "data", "history", d)
    os.makedirs(hist_dir, exist_ok=True)
    hist_kpi_path = os.path.join(hist_dir, "inbound_kpi_summary.json")
    
    hist_kpi = {
        "op_date": d,
        "contract_version": "2.0.0",
        "forecast_total": r['forecast_total'],
        "rot_hom_truoc": r['rot_hom_truoc'],
        "rot_hom_nay": r['rot_hom_nay'],
        "rot_ton_dong": r['rot_ton_dong']
    }
    
    with open(hist_kpi_path, 'w', encoding='utf-8') as f:
        json.dump(hist_kpi, f, ensure_ascii=False, indent=2)

lu_data["daily_snapshots"] = daily_snaps
lu_data["rot_hom_truoc"] = results['2026-08-01']['rot_hom_truoc']
lu_data["rot_hom_nay"] = results['2026-08-01']['rot_hom_nay']

with open(last_update_path, 'w', encoding='utf-8') as f:
    json.dump(lu_data, f, ensure_ascii=False, indent=2)

conn.close()

print("=== BẢNG CHỐT FORECAST KPI KẾT QUẢ CHO CÁC NGÀY 27, 28, 29, 30, 31/07 VÀ HÔM NAY 01/08 ===")
print(f"{'Ngày':<12} | {'Rớt hôm trước':<15} | {'Rớt hôm nay':<15} | {'Tồn đọng':<15} | {'Forecast Total':<15}")
print("-" * 80)
for d in dates:
    r = results[d]
    rht = f"{r['rot_hom_truoc']:,}"
    rhn = f"{r['rot_hom_nay']:,}"
    rtd = f"{r['rot_ton_dong']:,}"
    fct = f"{r['forecast_total']:,}"
    print(f"{d:<12} | {rht:>15} | {rhn:>15} | {rtd:>15} | {fct:>15}")
