import sys

sys.stdout.reconfigure(encoding='utf-8')

fn = 'backend_sync/sync_postgre.py'

with open(fn, 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Update main live payload in sync_postgre.py
old_block_1 = '''    fc_shuttle = sum(stats['volume'] for (st, pk, status, in_op, fc_op, *rest), stats in inbound_group.items() if status not in ('Inbound', 'Outbound') and not (st.strip().upper().startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or pk.strip().upper().startswith(('BN HUB', 'HN ', 'HD ', 'HY '))))
    fc_linehaul = sum(stats['volume'] for (st, pk, status, in_op, fc_op, *rest), stats in inbound_group.items() if status not in ('Inbound', 'Outbound') and (st.strip().upper().startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or pk.strip().upper().startswith(('BN HUB', 'HN ', 'HD ', 'HY '))))
    inbound_kpi_summary = {
        "op_date": today,
        "contract_version": "2.0.0",
        "inbound_orders": total_inbound_today,
        "inbound_weight_ton": round(sum(stats['weight_kg'] for (st, pk, status, in_op, *rest), stats in inbound_group.items() if status == 'Inbound' and in_op == today) / 1000.0, 3),
        "forecast_total": fc_shuttle + fc_linehaul,
        "shuttle": fc_shuttle,
        "linehaul": fc_linehaul
    }'''

new_block_1 = '''    fc_orders_now = sum(stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items() if status not in ('Inbound', 'Outbound') and fc_op == today)
    fc_orders_live = sum(stats['volume'] for (st, pk, status, in_op, fc_op, pk_op, ar_op, *rest), stats in inbound_group.items() if status not in ('Inbound', 'Outbound') and fc_op < today)
    inbound_kpi_summary = {
        "op_date": today,
        "contract_version": "2.0.0",
        "inbound_orders": total_inbound_today,
        "inbound_weight_ton": round(sum(stats['weight_kg'] for (st, pk, status, in_op, *rest), stats in inbound_group.items() if status == 'Inbound' and in_op == today) / 1000.0, 3),
        "forecast_total": fc_orders_now + fc_orders_live,
        "orders_now": fc_orders_now,
        "orders_live": fc_orders_live
    }'''

if old_block_1 in c:
    c = c.replace(old_block_1, new_block_1)
    print("Replaced live KPI summary payload in sync_postgre.py!")
else:
    print("WARNING: Could not find old_block_1 in sync_postgre.py!")

# 2. Update historical KPI summary payload in sync_postgre.py
old_block_2 = '''                h_kpi = {
                    "op_date": h_d,
                    "contract_version": "2.0.0",
                    "inbound_orders": inb_c,
                    "inbound_weight_ton": inb_w,
                    "forecast_total": tr_c + pk_c + cr_c,
                    "rot_hom_truoc": 17 if h_d == '2026-07-31' else 0,
                    "rot_hom_nay": tr_c + pk_c,
                    "linehaul_bn_hub": 0
                }'''

new_block_2 = '''                h_kpi = {
                    "op_date": h_d,
                    "contract_version": "2.0.0",
                    "inbound_orders": inb_c,
                    "inbound_weight_ton": inb_w,
                    "forecast_total": tr_c + pk_c + cr_c,
                    "orders_now": cr_c,
                    "orders_live": tr_c + pk_c
                }'''

if old_block_2 in c:
    c = c.replace(old_block_2, new_block_2)
    print("Replaced historical KPI summary payload in sync_postgre.py!")
else:
    print("WARNING: Could not find old_block_2 in sync_postgre.py!")

with open(fn, 'w', encoding='utf-8') as f:
    f.write(c)

print("backend_sync/sync_postgre.py updated successfully!")
