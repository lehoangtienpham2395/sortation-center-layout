import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Removing v2.2 FIXED badge from main header in InboundDashboard.tsx and InboundDashboardV2.tsx...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    badge_snippet = '<span style={{ fontSize: \'13px\', color: \'#00e5ff\', verticalAlign: \'middle\', background: \'rgba(0,229,255,0.12)\', padding: \'2px 8px\', borderRadius: \'6px\', border: \'1px solid rgba(0,229,255,0.3)\' }}>v2.2 FIXED</span>'

    if badge_snippet in c:
        c = c.replace(badge_snippet, '')
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Successfully removed v2.2 FIXED badge from {fn}!")
    else:
        print(f"WARNING: Could not find badge_snippet in {fn}")

