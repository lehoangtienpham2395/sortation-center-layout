import psycopg2
import pandas as pd
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang2299', host='127.0.0.1', port=5433)

# Query detailed un-inbounded dispatch orders for 2026-08-03
query = '''
    SELECT 
        tracking as "Mã vận đơn",
        data_source as "Nguồn dữ liệu",
        COALESCE(pickup_station, station_name, '') as "Bưu cục đi/gửi",
        dispatch_code as "Mã chuyến/Sortcode",
        COALESCE(next_station, '') as "Bưu cục đến (Next Station)",
        status_sys as "Trạng thái",
        COALESCE(orders_num, 1) as "Số lượng",
        ROUND(COALESCE(orders_weight, 0)::numeric / 1000.0, 3) as "Trọng lượng (kg)",
        COALESCE(op_date_pickup::text, operation_date_created::text) as "Ngày vận hành",
        CASE 
            WHEN UPPER(rank) = 'LINEHAUL' OR UPPER(next_station) LIKE 'BN HUB%' OR UPPER(next_station) LIKE 'HN %' OR UPPER(next_station) LIKE 'HD %' OR UPPER(next_station) LIKE 'HY %' OR UPPER(pickup_station) LIKE 'BN HUB%' THEN 'Linehaul'
            ELSE 'Shuttle'
        END as "Phân loại Tuyến (Route)",
        CASE 
            WHEN UPPER(next_station) LIKE 'BN HUB%' THEN 'Bưu cục đến là BN HUB (Linehaul Miền Bắc)'
            WHEN UPPER(next_station) LIKE 'HN %' OR UPPER(next_station) LIKE 'HD %' OR UPPER(next_station) LIKE 'HY %' THEN 'Bưu cục đến thuộc cụm Miền Bắc/Đông Bắc'
            WHEN UPPER(rank) = 'LINEHAUL' THEN 'Cấp bậc tuyến là Linehaul'
            ELSE 'Bưu cục đến là Bưu cục/Trạm giao hàng nội tỉnh SG'
        END as "Lý do Phân loại"
    FROM enriched.dispatch_enriched
    WHERE status_sys NOT IN ('Inbound', 'Outbound')
      AND COALESCE(op_date_pickup::date, operation_date_created::date) = '2026-08-03'::date
    ORDER BY "Phân loại Tuyến (Route)" ASC, "Bưu cục đến (Next Station)" ASC;
'''

df = pd.read_sql_query(query, conn)
conn.close()

print(f"Total Forecast Rows for 2026-08-03: {len(df):,} rows")
print("\nBreakdown by Route Type:")
print(df['Phân loại Tuyến (Route)'].value_counts())

print("\nTop 15 Destination Stations for Shuttle:")
print(df[df['Phân loại Tuyến (Route)'] == 'Shuttle']['Bưu cục đến (Next Station)'].value_counts().head(15))

print("\nTop 15 Destination Stations for Linehaul:")
print(df[df['Phân loại Tuyến (Route)'] == 'Linehaul']['Bưu cục đến (Next Station)'].value_counts().head(15))

# Export CSV to artifacts directory
artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
out_csv = os.path.join(artifact_dir, "danh_sach_chi_tiet_11496_don_forecast_shuttle_linehaul_03082026.csv")
df.to_csv(out_csv, index=False, encoding='utf-8-sig')

print(f"\nCSV exported successfully to: {out_csv}")
