"""
fix_daily_snapshots.py
Cập nhật daily_snapshots trong last_update.json
từ public/data/history/YYYY-MM-DD/inbound_kpi_summary.json (source of truth)
"""
import os, json, glob, sys
sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST_UPDATE  = os.path.join(PROJECT_ROOT, 'data', 'last_update.json')
HIST_DIR     = os.path.join(PROJECT_ROOT, 'public', 'data', 'history')

# Load last_update.json
with open(LAST_UPDATE, encoding='utf-8') as f:
    lu = json.load(f)

old_snaps = lu.get('daily_snapshots', {})
new_snaps = {}

# Đọc từng ngày trong public/data/history/
kpi_files = glob.glob(os.path.join(HIST_DIR, '????-??-??', 'inbound_kpi_summary.json'))
for kpi_path in sorted(kpi_files):
    date = os.path.basename(os.path.dirname(kpi_path))
    try:
        with open(kpi_path, encoding='utf-8') as f:
            kpi = json.load(f)

        # Lấy ngày hôm nay (live date không freeze)
        active_date = lu.get('active_date', '')
        is_frozen   = (date != active_date)

        new_snaps[date] = {
            'forecast_total':  kpi.get('forecast_total', 0),
            'inbound_orders':  kpi.get('inbound_orders', 0),
            'shuttle':         kpi.get('shuttle', 0),
            'linehaul':        kpi.get('linehaul', 0),
            'rot_hom_truoc':   kpi.get('rot_hom_truoc', 0),
            'rot_hom_nay':     kpi.get('rot_hom_nay', 0),
            'is_frozen':       is_frozen,
        }
        old = old_snaps.get(date, {})
        old_fc  = old.get('forecast_total', old.get('rot_hom_nay', '?'))
        new_fc  = new_snaps[date]['forecast_total']
        changed = '✅' if old_fc != new_fc else '  '
        print(f"  {changed} {date}: forecast {old_fc} → {new_fc}, inbound {new_snaps[date]['inbound_orders']:,}, frozen={is_frozen}")
    except Exception as e:
        print(f"  ⚠️  {date}: {e}")

# Ghi lại last_update.json
lu['daily_snapshots'] = new_snaps
with open(LAST_UPDATE, 'w', encoding='utf-8') as f:
    json.dump(lu, f, ensure_ascii=False, indent=2)

print(f"\n✅ last_update.json updated: {len(new_snaps)} ngày trong daily_snapshots")
