import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

df_all = pd.read_excel('DS_Don_BN_HUB_DuBao_2026-08-20_3984.xlsx')
df_today = df_all[df_all['Ngày vận hành'] == '2026-08-20'].copy()

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p_today_xlsx = os.path.join(base_dir, f"DS_Don_BN_HUB_RiengHomNay_2026-08-20_{len(df_today)}.xlsx")
p_today_csv = os.path.join(base_dir, f"DS_Don_BN_HUB_RiengHomNay_2026-08-20_{len(df_today)}.csv")

df_today.to_excel(p_today_xlsx, index=False)
df_today.to_csv(p_today_csv, index=False, encoding='utf-8-sig')

print(f"✅ Đã lưu file riêng hôm nay: {p_today_xlsx}")
