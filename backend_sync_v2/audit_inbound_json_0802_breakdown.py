import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Auditing data/inbound.json for 2026-08-02...")

with open('data/inbound.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

rows = data if isinstance(data, list) else data.get('data', [])

# Audit rows matching 2026-08-02 under various date fields
fc_orders = {}
fc_weights = {}

for r in rows:
    status = r.get('status') or r.get('Trạng thái') or r.get('Trng thi') or ''
    if status != 'Inbound' and status != 'Đã nhập kho':
        continue

    # Get operating date
    d_fc = str(r.get('op_date_forecast') or r.get('Ngày vận hành_Forecast') or '')
    d_inb = str(r.get('op_date_inbound') or r.get('Ngày vận hành_Inbound') or '')
    d_crt = str(r.get('op_date_created') or r.get('Ngày vận hành_Created') or '')
    d_pk = str(r.get('op_date_pickup') or r.get('Ngày vận hành_Pickup') or '')
    d_op = str(r.get('op_date') or r.get('Ngày vận hành') or '')

    # Check match with 2026-08-02
    if '2026-08-02' not in (d_fc + d_inb + d_crt + d_pk + d_op):
        continue

    pst = (r.get('pickup_station') or r.get('send_network') or r.get('Bưu cục') or 'Chưa rõ').strip()
    if 'BN HUB' in pst.upper():
        pst = 'BN HUB'

    vol = int(r.get('volume') or r.get('Volume') or 1)
    wt = float(r.get('weight_ton') or r.get('Weight') or 0)

    fc_orders[pst] = fc_orders.get(pst, 0) + vol
    fc_weights[pst] = fc_weights.get(pst, 0) + wt

print("=== Inbound JSON Breakdown for 2026-08-02 ===")
sorted_fcs = sorted(fc_orders.items(), key=lambda x: x[1], reverse=True)
for fc, cnt in sorted_fcs[:10]:
    print(f"{fc}: {cnt} đơn, {fc_weights[fc]:.1f} Tấn")

print(f"\nTotal Inbound Orders on 2026-08-02: {sum(fc_orders.values())}")
print(f"Total Inbound Weight on 2026-08-02: {sum(fc_weights.values()):.1f} Tấn")
