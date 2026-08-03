import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing isFutureDate bug that forced all metrics to 0 for 2026-08-03...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_logic = 'const isFutureDate = normActiveDate > todayOpDate;'
    new_logic = '''const maxAvailableDate = (inboundDates && inboundDates.length > 0) 
    ? normalizeDateStr(inboundDates[inboundDates.length - 1]) 
    : todayOpDate;
  const isFutureDate = normActiveDate > maxAvailableDate;'''

    if old_logic in c:
        c = c.replace(old_logic, new_logic)
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Successfully fixed isFutureDate bug in {fn}!")
    else:
        print(f"WARNING: Could not find old_logic in {fn}")

print("✅ isFutureDate bug resolved!")
