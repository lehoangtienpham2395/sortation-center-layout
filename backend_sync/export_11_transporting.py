import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

df_2211 = pd.read_excel('DS_Don_BN_HUB_DuBao_2211.xlsx')
df_11 = df_2211[df_2211['Trạng thái hệ thống'] == 'Transporting'].copy()

# Add explanation column
df_11['Lý do'] = 'Đang trên xe tải trung chuyển từ bưu cục gửi về HUB (Trạng thái Transporting)'

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p_xlsx = os.path.join(base_dir, 'DS_11_Don_Transporting_Chua_Vao_Linehaul.xlsx')
p_csv = os.path.join(base_dir, 'DS_11_Don_Transporting_Chua_Vao_Linehaul.csv')

df_11.to_excel(p_xlsx, index=False)
df_11.to_csv(p_csv, index=False, encoding='utf-8-sig')

print(f"✅ Đã lưu: {p_xlsx}")
