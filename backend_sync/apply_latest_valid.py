import os, shutil, pandas as pd
from sync_postgre import get_pg_conn

# File nguồn chính xác mà người dùng chỉnh sửa
src_valid = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync\config\valid.csv"

# Các đích đồng bộ đồng nhất
dest_desktop_valid = r"C:\Users\lehoa\OneDrive\Desktop\testing\Exportauto\Valid\valid.csv"
dest_root_valid = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\config\valid.csv"
dest_kpi_valid = r"C:\Users\lehoa\.gemini\antigravity\scratch\kpi-hub\data\valid.csv"

print(f"🔄 Đang nạp file valid.csv từ nguồn chuẩn người dùng: {src_valid}")
df_new = pd.read_csv(src_valid, encoding='utf-8-sig')
print(f"✅ Đã đọc valid.csv ({len(df_new):,} dòng, {len(df_new.columns)} cột)")

# Sao chép đồng bộ sang các thư mục khác
for dst in [dest_desktop_valid, dest_root_valid, dest_kpi_valid]:
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src_valid, dst)
        print(f"   📋 Đã đồng bộ sang: {dst}")
    except Exception as e_cp:
        print(f"   ⚠️ Không thể copy sang {dst}: {e_cp}")

# Cập nhật PostgreSQL dim.dim_valid_mapping
conn = get_pg_conn()
cur = conn.cursor()
try:
    cur.execute("TRUNCATE TABLE dim.dim_valid_mapping;")
    inserted_count = 0
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
            inserted_count += 1
    conn.commit()
    print(f"✅ Đã nạp thành công {inserted_count:,} dòng vào bảng dim.dim_valid_mapping trên PostgreSQL!")
except Exception as e:
    print(f"⚠️ Lỗi update dim_valid_mapping: {e}")
finally:
    conn.close()
