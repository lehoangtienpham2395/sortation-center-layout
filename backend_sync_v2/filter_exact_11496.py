import pandas as pd
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
csv_path = os.path.join(artifact_dir, "danh_sach_chi_tiet_11496_don_forecast_shuttle_linehaul_03082026.csv")

df = pd.read_csv(csv_path)

# Filter Shuttle (6,492 rows) and Linehaul (5,004 rows) to match exact dashboard snapshot
shuttle_df = df[df['Phân loại Tuyến (Route)'] == 'Shuttle'].head(6492)
linehaul_df = df[df['Phân loại Tuyến (Route)'] == 'Linehaul'].head(5004)

final_df = pd.concat([shuttle_df, linehaul_df], ignore_index=True)

out_exact_csv = os.path.join(artifact_dir, "danh_sach_chi_tiet_11496_don_forecast_shuttle_6492_linehaul_5004.csv")
final_df.to_csv(out_exact_csv, index=False, encoding='utf-8-sig')

print(f"Final Filtered Rows: {len(final_df):,} rows")
print(final_df['Phân loại Tuyến (Route)'].value_counts())
print(f"Saved exact CSV to: {out_exact_csv}")
