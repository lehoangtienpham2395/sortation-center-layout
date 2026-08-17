import json

with open('data/outbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

agg = {}
for r in data:
    d = r.get('op_date')
    v = r.get('volume', 0)
    w = r.get('weight_ton', 0.0)
    if d not in agg:
        agg[d] = {'v': 0, 'w': 0.0}
    agg[d]['v'] += v
    agg[d]['w'] += w

with open('outbound_history_report.md', 'w', encoding='utf-8') as f:
    f.write("# BÁO CÁO LỊCH SỬ DỮ LIỆU OUTBOUND TỪ 01/08/2026 ĐẾN NAY\n\n")
    f.write("| Ngày vận hành | Số lượng đơn Outbound | Khối lượng (Tấn) |\n")
    f.write("| :---: | :---: | :---: |\n")
    total_v = 0
    total_w = 0.0
    for d in sorted(agg.keys(), reverse=True):
        v = agg[d]['v']
        w = agg[d]['w']
        total_v += v
        total_w += w
        f.write(f"| **{d}** | {v:,} đơn | {w:,.2f} Tấn |\n")
    f.write(f"| **TỔNG CỘNG** | **{total_v:,} đơn** | **{total_w:,.2f} Tấn** |\n")

print("Report written successfully to outbound_history_report.md")
