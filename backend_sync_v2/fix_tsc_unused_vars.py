import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing TS6133 unused variables (isInbound, isForecastMember) across React components...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if 'const isInbound = ' in line or 'let isForecastMember = ' in line:
            continue
        new_lines.append(line)

    with open(fn, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"Removed unused variables from {fn}!")

print("✅ Unused TypeScript variables removed!")
