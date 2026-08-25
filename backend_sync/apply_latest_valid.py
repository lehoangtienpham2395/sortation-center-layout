import os, shutil, pandas as pd
from sync_postgre import get_pg_conn

src_valid = r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv"
dest_sync_valid = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync\config\valid.csv"
dest_root_valid = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\config\valid.csv"

print(f"🔄 Đang sao chép file valid mới nhất từ: {src_valid}")
shutil.copy2(src_valid, dest_sync_valid)
if os.path.exists(os.path.dirname(dest_root_valid)):
    shutil.copy2(src_valid, dest_root_valid)

df_new = pd.read_csv(dest_sync_valid, encoding='utf-8-sig')
print(f"✅ Đã nạp valid.csv mới ({len(df_new):,} dòng, {len(df_new.columns)} cột)")
print("Columns:", list(df_new.columns))

# Cập nhật PostgreSQL dim.dim_valid_mapping
conn = get_pg_conn()
cur = conn.cursor()
try:
    cur.execute("TRUNCATE TABLE dim.dim_valid_mapping;")
    for _, r in df_new.iterrows():
        st_final = str(r.get('Station_2') or r.get('Station_1') or r.get('Tên điểm tiếp theo') or '').strip()
        rd  = str(r.get('Round') or r.get('round') or '').strip()
        rk  = str(r.get('Rank') or r.get('rank') or '').strip()
        sc  = str(r.get('sortcode') or '').strip().upper()
        ar  = str(r.get('area') or r.get('Mã khu vực') or '').strip().upper()
        cap = 1400 if ar == 'A06' else 780
        
        if sc or st_final:
            cur.execute("""
                INSERT INTO dim.dim_valid_mapping (sortcode, station_final, round, rank, area_id, capacity, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING;
            """, (sc, st_final, rd, rk, ar, cap))
    conn.commit()
    print("✅ Đã đồng bộ valid mới vào bảng dim.dim_valid_mapping trên PostgreSQL!")
except Exception as e:
    print(f"⚠️ Lỗi update dim_valid_mapping: {e}")
finally:
    conn.close()
