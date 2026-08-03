import psycopg2
import csv
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Get column names of enriched.dispatch_enriched
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='enriched' AND table_name='dispatch_enriched';")
cols = [r[0] for r in cur.fetchall()]

# Select all fields for the 7,272 rot orders
cur.execute('''
    SELECT *
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::text, operation_date_created::text) LIKE '2026-07-31%%';
''')

rows = cur.fetchall()

rot_rows = []

col_idx_ref = cols.index('op_date_pickup') if 'op_date_pickup' in cols else cols.index('operation_date_created')
col_idx_flag_in = cols.index('flag_inbound') if 'flag_inbound' in cols else -1
col_idx_op_in = cols.index('operation_date_inbound') if 'operation_date_inbound' in cols else -1
col_idx_in_date = cols.index('inbound_scandate') if 'inbound_scandate' in cols else -1
col_idx_flag_out = cols.index('flag_outbound') if 'flag_outbound' in cols else -1
col_idx_out_date = cols.index('outbound_scandate') if 'outbound_scandate' in cols else -1
col_idx_status = cols.index('status_sys') if 'status_sys' in cols else -1

for row in rows:
    ref_d = row[col_idx_ref] if col_idx_ref >= 0 else None
    flag_in = row[col_idx_flag_in] if col_idx_flag_in >= 0 else None
    op_in = row[col_idx_op_in] if col_idx_op_in >= 0 else None
    in_date = row[col_idx_in_date] if col_idx_in_date >= 0 else None
    flag_out = row[col_idx_flag_out] if col_idx_flag_out >= 0 else None
    out_date = row[col_idx_out_date] if col_idx_out_date >= 0 else None
    st_sys = row[col_idx_status] if col_idx_status >= 0 else None
    
    is_canc = (str(st_sys or '').strip() == 'Đã hủy')
    has_in_cond = (flag_in == 1 or op_in is not None or in_date is not None)
    has_out_cond = (flag_out == 1 or out_date is not None)
    
    is_rot = (not has_in_cond) and (not has_out_cond) and (not is_canc)
    
    if is_rot:
        rot_rows.append(row)

# Artifact destination path
artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
csv_filename = "danh_sach_7272_don_rot_hom_truoc_31072026.csv"
csv_filepath = os.path.join(artifact_dir, csv_filename)

with open(csv_filepath, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(cols)
    writer.writerows(rot_rows)

conn.close()

print(f"Exported successfully {len(rot_rows):,} orders to:")
print(csv_filepath)
