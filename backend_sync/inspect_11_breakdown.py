import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

# Load the 2,211 file
df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')

# Load the exact items in inv_group for A06 from sync_postgre
# Let's inspect the 11 orders in df_2211 that are:
# 1. next_station == 'Chưa phân vùng' (nhưng dispatch_code là mã Bắc)
# 2. status_sys == 'Transporting'
print("--- Breakdown of 2,211 orders by Next Station ---")
print(df_2211['Điểm tiếp theo (Next Station)'].value_counts())

print("\n--- Breakdown of 2,211 orders by Trạng thái ---")
print(df_2211['Trạng thái hệ thống'].value_counts())

print("\n--- Breakdown of 2,211 orders by Luồng vận chuyển ---")
print(df_2211['Luồng vận chuyển'].value_counts())

# Check the 11 orders that have status Transporting or special
df_11_trans = df_2211[df_2211['Trạng thái hệ thống'] == 'Transporting']
print(f"\n--- 11 Đơn có Trạng thái 'Transporting' ({len(df_11_trans)} đơn) ---")
print(df_11_trans[['Mã vận đơn', 'Trạng thái hệ thống', 'Bưu cục gửi (Pickup Station)', 'Điểm tiếp theo (Next Station)', 'Mã điều phối (Dispatch Code)', 'Khối lượng tính cước (Kg)']].to_string())
