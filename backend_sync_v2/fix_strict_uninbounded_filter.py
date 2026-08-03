import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Helper check for strict un-inbounded and un-outbounded rows
# Check for ANY scan timestamp or status matching Inbound/Outbound/Canceled

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # Old condition
    old_cond = "if (!isInbound && status !== 'Outbound' && !d['Inbound Time'] && !d['inbound_time'] && !d['Outbound Time'] && !d['outbound_time']) {"
    
    # New strict condition checking ALL possible scan field names
    new_cond = '''const hasInboundScan = Boolean(
        d['inbound_scandate'] || d['Inbound Time'] || d['inbound_time'] || d['Inbound_time'] || d['inbound_date'] || d['Ngày nhập kho'] || d['Ngay nhap kho']
      );
      const hasOutboundScan = Boolean(
        d['outbound_scandate'] || d['Outbound Time'] || d['outbound_time'] || d['Outbound_time'] || d['outbound_date'] || d['Ngày xuất kho'] || d['Ngay xuat kho']
      );
      const isDoneStatus = ['Inbound', 'Outbound', 'Canceled', 'Đã nhập kho', 'Đã xuất kho', 'Đã hủy'].includes(status);

      if (!isDoneStatus && !hasInboundScan && !hasOutboundScan) {'''

    if old_cond in c:
        c = c.replace(old_cond, new_cond)
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Successfully updated strict filter condition in {fn}")
    else:
        print(f"WARNING: Could not find old_cond in {fn}")

