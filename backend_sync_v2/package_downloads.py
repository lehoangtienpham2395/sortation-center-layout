import os
import shutil
import zipfile
import sys

sys.stdout.reconfigure(encoding='utf-8')

artifact_dir = r"C:\Users\lehoa\.gemini\antigravity\brain\00e77204-b52a-4e7c-9a23-9a846e4b80f0"
csv_path = os.path.join(artifact_dir, "danh_sach_chi_tiet_11496_don_forecast_shuttle_6492_linehaul_5004.csv")

# 1. Zip file to drastically reduce size and prevent browser freezing
zip_path = os.path.join(artifact_dir, "danh_sach_chi_tiet_11496_don_forecast.zip")
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(csv_path, arcname="danh_sach_chi_tiet_11496_don_forecast.csv")

# 2. Copy to public/downloads for HTTP local server download
public_dl_dir = r"C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\public\downloads"
os.makedirs(public_dl_dir, exist_ok=True)

dest_csv = os.path.join(public_dl_dir, "danh_sach_11496_don_forecast.csv")
dest_zip = os.path.join(public_dl_dir, "danh_sach_11496_don_forecast.zip")

shutil.copyfile(csv_path, dest_csv)
shutil.copyfile(zip_path, dest_zip)

print(f"Zip created: {zip_path} ({os.path.getsize(zip_path):,} bytes)")
print(f"Copied to public downloads: {dest_csv} & {dest_zip}")
