import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing BN HUB origin station grouping logic in React components...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_fc_block = '''      let rawFcName = d.pickup_station || d.send_network || d['Bưu cục nộp'] || d['Bưu cục gốc'] || d['Bưu cục'] || d['Bu cc'] || d.station_name || 'Chưa rõ';
      if (isNorthRow(d)) {
        rawFcName = 'BN HUB';
      }'''

    new_fc_block = '''      const pSt = String(d.pickup_station || d.send_network || d['Bưu cục nộp'] || d['Bưu cục gốc'] || d['Bưu cục'] || d['Bu cc'] || d.station_name || '').trim();
      let rawFcName = pSt || 'Chưa rõ';
      if (pSt.toUpperCase().includes('BN HUB') || isNorthRow(pSt)) {
        rawFcName = 'BN HUB';
      }'''

    if old_fc_block in c:
        c = c.replace(old_fc_block, new_fc_block)
        print(f"Successfully fixed BN HUB station grouping in {fn}!")
    else:
        print(f"WARNING: Could not find old_fc_block in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ BN HUB origin station grouping logic updated!")
