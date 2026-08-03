import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing missing numbers issue across App.tsx and InboundDashboard.tsx...")

# 1. Update App.tsx default selectedInboundDate to '2026-08-03'
with open('src/App.tsx', 'r', encoding='utf-8') as f:
    c_app = f.read()

c_app = c_app.replace(
    "const [selectedInboundDate, setSelectedInboundDate] = useState<string>('');",
    "const [selectedInboundDate, setSelectedInboundDate] = useState<string>('2026-08-03');"
)

with open('src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(c_app)

print("Updated App.tsx default selectedInboundDate to '2026-08-03'!")

# 2. Update getFcOpDate and isOpMatch in InboundDashboard.tsx and InboundDashboardV2.tsx
for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # Expand getFcOpDate to include op_date_created, op_date, etc.
    old_fc_op = '''  const getFcOpDate = (row: any) => {
    return normalizeDateStr(row['op_date_forecast'] || row['Ngy vn hnh_Forecast'] || row['Ngày vận hành_Forecast'] || '');
  };'''

    new_fc_op = '''  const getFcOpDate = (row: any) => {
    return normalizeDateStr(
      row['op_date_created'] || row['Ngày vận hành_Created'] || row['Ngy vn hnh_Created'] || 
      row['op_date_forecast'] || row['Ngy vn hnh_Forecast'] || row['Ngày vận hành_Forecast'] || 
      row['op_date'] || row['Ngày vận hành'] || row['Ngy vn hnh'] || ''
    );
  };'''

    if old_fc_op in c:
        c = c.replace(old_fc_op, new_fc_op)

    old_match = '''      const arrOpDate = normalizeDateStr(d['op_date_arrival'] || d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'] || (d['Arrival Time'] ? getOperatingDateFromTimestamp(d['Arrival Time']) : ''));
      const pkOpDate  = normalizeDateStr(d['op_date_pickup']  || d['Ngày vận hành_Pickup']  || d['Ngy vn hnh_Pickup']  || '');
      const inbOpDate = normalizeDateStr(d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'] || '');

      const isOpMatch = (normFcDate === normActiveDate) || (arrOpDate === normActiveDate) || (pkOpDate === normActiveDate) || (inbOpDate === normActiveDate);'''

    new_match = '''      const crtOpDate = normalizeDateStr(d['op_date_created'] || d['Ngày vận hành_Created'] || d['Ngy vn hnh_Created'] || d['op_date'] || d['Ngày vận hành'] || '');
      const arrOpDate = normalizeDateStr(d['op_date_arrival'] || d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'] || (d['Arrival Time'] ? getOperatingDateFromTimestamp(d['Arrival Time']) : ''));
      const pkOpDate  = normalizeDateStr(d['op_date_pickup']  || d['Ngày vận hành_Pickup']  || d['Ngy vn hnh_Pickup']  || '');
      const inbOpDate = normalizeDateStr(d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'] || '');

      const isOpMatch = (normFcDate === normActiveDate) || (crtOpDate === normActiveDate) || (arrOpDate === normActiveDate) || (pkOpDate === normActiveDate) || (inbOpDate === normActiveDate);'''

    if old_match in c:
        c = c.replace(old_match, new_match)

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

    print(f"Updated date match logic in {fn}!")

print("✅ Fixed missing numbers issue!")
