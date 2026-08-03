import psycopg2
import json
import csv
import sys
import os
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Get column names of enriched.dispatch_enriched
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='enriched' AND table_name='dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]

dates = ['2026-07-27', '2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31', '2026-08-01']

results = {}
rot_769_rows = []

col_idx_ref = cols.index('op_date_pickup') if 'op_date_pickup' in cols else cols.index('operation_date_created')
col_idx_flag_in = cols.index('flag_inbound') if 'flag_inbound' in cols else -1
col_idx_flag_out = cols.index('flag_outbound') if 'flag_outbound' in cols else -1
col_idx_status = cols.index('status_sys') if 'status_sys' in cols else -1
col_idx_pk = cols.index('pickup_station') if 'pickup_station' in cols else -1
col_idx_next = cols.index('next_station') if 'next_station' in cols else -1
col_idx_rank = cols.index('rank') if 'rank' in cols else -1
col_idx_round = cols.index('round') if 'round' in cols else -1

for target_date in dates:
    prev_date = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    
    cur.execute('''
        SELECT *
        FROM enriched.dispatch_enriched
        WHERE COALESCE(op_date_pickup::date, operation_date_created::date) <= %s::date;
    ''', (target_date,))
    
    rows = cur.fetchall()
    
    rot_hom_truoc = 0
    rot_hom_nay = 0
    rot_ton_dong = 0
    
    for row in rows:
        ref_d = row[col_idx_ref] if col_idx_ref >= 0 else None
        has_in = row[col_idx_flag_in] if col_idx_flag_in >= 0 else 0
        has_out = row[col_idx_flag_out] if col_idx_flag_out >= 0 else 0
        st_sys = row[col_idx_status] if col_idx_status >= 0 else ''
        pk_st = str(row[col_idx_pk] or '').strip().upper()
        next_st = str(row[col_idx_next] or '').strip().upper()
        rk = str(row[col_idx_rank] or '').strip().upper()
        rd = str(row[col_idx_round] or '').strip().upper()
        
        is_canceled = (st_sys == 'Đã hủy')
        is_north = ('BN HUB' in pk_st or 'BN HUB' in next_st or 'BN HUB' in rk or 'LINEHAUL' in rd or pk_st.startswith(('HN ', 'HD ', 'HY ')))
        
        is_rot = (not has_in) and (not has_out) and (not is_canceled) and (not is_north)
        
        if is_rot and ref_d:
            ref_d_str = str(ref_d)[:10]
            if ref_d_str == target_date:
                rot_hom_nay += 1
            elif ref_d_str == prev_date:
                rot_hom_truoc += 1
                if target_date == '2026-08-01':
                    rot_769_rows.append(row)
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

# Export clean 769 South orders CSV
artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
csv_filepath = os.path.join(artifact_dir, "danh_sach_769_don_rot_hom_truoc_hcm_hub.csv")

with open(csv_filepath, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(cols)
    writer.writerows(rot_769_rows)

BASE_DIR = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"
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

print("=== BẢNG CHỐT FORECAST KPI CHUẨN XÁC SAU KHI TÁCH KHÓA MIỀN BẮC/BN HUB LINEHAUL ===")
print(f"{'Ngày':<12} | {'Rớt hôm trước':<15} | {'Rớt hôm nay':<15} | {'Tồn đọng':<15} | {'Forecast Total':<15}")
print("-" * 80)
for d in dates:
    r = results[d]
    rht = f"{r['rot_hom_truoc']:,}"
    rhn = f"{r['rot_hom_nay']:,}"
    rtd = f"{r['rot_ton_dong']:,}"
    fct = f"{r['forecast_total']:,}"
    print(f"{d:<12} | {rht:>15} | {rhn:>15} | {rtd:>15} | {fct:>15}")

print(f"\n✅ Đã xuất {len(rot_769_rows):,} đơn chuẩn Rớt hôm trước HCM HUB/Miền Nam vào file:")
print(csv_filepath)
