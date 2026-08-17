import json
import pandas as pd

with open('data/inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)

a06_items = [x for x in inv if x.get('area_id') == 'A06' or x.get('station_name') == 'BN HUB']
df = pd.DataFrame(a06_items)

with open('bn_hub_final_summary.md', 'w', encoding='utf-8') as f:
    f.write("# TỔNG HỢP SỐ LIỆU BN HUB (CHUTE A06 / LINEHAUL) SAU ĐỐI SOÁT\n\n")
    
    total_vol = df['volume'].sum()
    total_wt = df['weight_ton'].sum()
    f.write(f"- **Tổng số lượng đơn BN HUB cần xử lý:** **{total_vol:,} đơn**\n")
    f.write(f"- **Tổng khối lượng:** **{total_wt:,.3f} Tấn** (~ **{round(total_wt, 1)} Tấn**)\n\n")
    
    f.write("## 1. Phân bổ theo Ngày tạo / Vận hành\n\n")
    f.write("| Ngày vận hành | Số lượng đơn | Khối lượng (Tấn) | Tỷ trọng |\n")
    f.write("| :---: | :---: | :---: | :---: |\n")
    
    summary_date = df.groupby('op_date')[['volume', 'weight_ton']].sum().reset_index()
    summary_date = summary_date.sort_values(by='op_date', ascending=False)
    for _, r in summary_date.iterrows():
        pct = (r['volume'] / total_vol) * 100
        f.write(f"| **{r['op_date']}** | {int(r['volume']):,} đơn | {r['weight_ton']:,.3f} Tấn | {pct:.1f}% |\n")
        
    f.write("\n## 2. Phân bổ theo Trạng thái vận hành\n\n")
    f.write("| Trạng thái | Số lượng đơn | Khối lượng (Tấn) | Tỷ trọng |\n")
    f.write("| :---: | :---: | :---: | :---: |\n")
    
    summary_stt = df.groupby('status')[['volume', 'weight_ton']].sum().reset_index()
    for _, r in summary_stt.iterrows():
        pct = (r['volume'] / total_vol) * 100
        f.write(f"| **{r['status']}** | {int(r['volume']):,} đơn | {r['weight_ton']:,.3f} Tấn | {pct:.1f}% |\n")

print("Done generating bn_hub_final_summary.md")
