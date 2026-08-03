import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Removing tilde '~' character from Forecast Card Weight label...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_str = "(~{totalForecastWeight.toFixed(1).replace('.', ',')} Tấn)"
    new_str = "({totalForecastWeight.toFixed(1).replace('.', ',')} Tấn)"

    if old_str in c:
        c = c.replace(old_str, new_str)
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Successfully removed '~' in {fn}")
    else:
        print(f"WARNING: Could not find old_str in {fn}")

