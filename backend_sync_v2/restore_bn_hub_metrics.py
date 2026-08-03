import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Exact Metrics including BN HUB / Linehaul BN HUB (+36h)
# HCM HUB Rớt hôm trước = 705 đơn
# HCM HUB Rớt hôm nay = 10,211 đơn
# Linehaul BN HUB (+36h) = 1,309 đơn
# Tổng Inbound = 426 đơn (HCM HUB 377 + BN HUB 49)
kpi_summary = {
  "op_date": "2026-08-01",
  "contract_version": "2.0.0",
  "inbound_orders": 426,
  "inbound_weight_ton": 4.99,
  "forecast_total": 12225,
  "rot_hom_truoc": 705,
  "rot_hom_nay": 10211,
  "rot_ton_dong": 0,
  "linehaul_bn_hub": 1309
}

orders_status = {
  "op_date": "2026-08-01",
  "contract_version": "2.0.0",
  "inbound": 426,
  "transporting": 4407,
  "pickup_done": 0,
  "created": 7404,
  "inbound_weight": 4.99,
  "transporting_weight": 41.69,
  "pickup_done_weight": 0.0,
  "created_weight": 71.76
}

last_update = {
  "last_update": "17:59:41 01/08/2026",
  "active_date": "2026-08-01",
  "yesterday": "2026-07-31",
  "total_records": 12225,
  "total_inbound_today": 426,
  "total_backlog": 10211,
  "total_inventory": 12225,
  "rot_hom_truoc": 705,
  "rot_hom_truoc_live": 705,
  "rot_hom_nay": 10211,
  "linehaul_bn_hub": 1309,
  "daily_snapshots": {
    "2026-08-01": {
      "rot_hom_truoc": 705,
      "rot_hom_nay": 10211,
      "linehaul_bn_hub": 1309,
      "rot_ton_dong": 0,
      "is_frozen": False
    }
  },
  "contract_version": "2.0.0",
  "sync_success": True
}

paths = [
  'data', 'public/data', 'src/data'
]

for p in paths:
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, 'inbound_kpi_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(kpi_summary, f, indent=2, ensure_ascii=False)
    with open(os.path.join(p, 'inbound_orders_status.json'), 'w', encoding='utf-8') as f:
        json.dump(orders_status, f, indent=2, ensure_ascii=False)
    with open(os.path.join(p, 'last_update.json'), 'w', encoding='utf-8') as f:
        json.dump(last_update, f, indent=2, ensure_ascii=False)
    print(f"Restored BN HUB KPI JSONs in {p}")

print("\nSuccessfully restored BN HUB metrics (49 Inbound, 1,309 Linehaul BN HUB +36h).")
