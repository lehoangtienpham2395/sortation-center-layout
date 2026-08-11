import psycopg2
import pandas as pd
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=== ĐANG XUẤT FILE DANH SÁCH ĐƠN VOLUME CHƯA OUTBOUND ===")

conn = psycopg2.connect(
    dbname='logistics_db',
    user='postgres',
    password='Tien@giang0203',
    host='127.0.0.1',
    port=5433
)

sql = """
    SELECT 
        tracking AS "Mã vận đơn",
        data_source AS "Nguồn dữ liệu",
        status_sys AS "Trạng thái hệ thống",
        pickup_station AS "Bưu cục gửi (Pickup Station)",
        next_station AS "Bưu cục nhận (Next Station)",
        flowtypedesc AS "Luồng vận chuyển",
        created_time AS "Thời gian tạo (Created)",
        pickup_time AS "Thời gian lấy (Pickup)",
        arrival_scandate AS "Thời gian đến bãi (Arrival)",
        inbound_scandate AS "Thời gian nhập kho (Inbound)",
        outbound_scandate AS "Thời gian xuất kho (Outbound)",
        operation_date_created AS "Ngày vận hành"
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created >= '2026-08-10'
    ORDER BY operation_date_created DESC, created_time DESC
"""

df = pd.read_sql(sql, conn)
conn.close()

# Bỏ timezone để export Excel không bị lỗi
for col in df.columns:
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        df[col] = df[col].dt.tz_localize(None)

print(f"Tổng số dòng chi tiết: {len(df):,} đơn hàng")

# Save file to project workspace root so user can easily download/view
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
out_csv  = os.path.join(base_dir, 'danh_sach_don_volume_chua_outbound.csv')
out_xlsx = os.path.join(base_dir, 'danh_sach_don_volume_chua_outbound.xlsx')

df.to_csv(out_csv, index=False, encoding='utf-8-sig')
print(f"✅ Đã xuất CSV: {out_csv}")

try:
    df.to_excel(out_xlsx, index=False, engine='openpyxl')
    print(f"✅ Đã xuất Excel: {out_xlsx}")
except Exception as e:
    print(f"Không thể xuất Excel (.xlsx): {e}")
