import os, sys, json, datetime

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

def build_history_index():
    """Scan public/data/history/ and build an index of available dates + summary stats."""
    history_root = os.path.join(PROJECT_ROOT, "public", "data", "history")
    
    if not os.path.exists(history_root):
        print("No history directory found.")
        return
    
    index_entries = []
    
    for d in sorted(os.listdir(history_root)):
        kpi_path = os.path.join(history_root, d, "inbound_kpi_summary.json")
        if not os.path.exists(kpi_path):
            continue
        try:
            with open(kpi_path, 'r', encoding='utf-8') as f:
                kpi = json.load(f)
            # Only include dates that have real data
            if kpi.get('forecast_total', 0) > 0 or kpi.get('inbound_orders', 0) > 0:
                index_entries.append({
                    "op_date": d,
                    "forecast_total": kpi.get('forecast_total', 0),
                    "inbound_orders": kpi.get('inbound_orders', 0),
                    "inbound_weight_ton": kpi.get('inbound_weight_ton', 0),
                    "shuttle": kpi.get('shuttle', 0),
                    "linehaul": kpi.get('linehaul', 0),
                })
        except Exception as e:
            print(f"  ⚠️ Skipping {d}: {e}")
    
    index_entries.sort(key=lambda x: x['op_date'], reverse=True)
    
    history_index = {
        "generated_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_dates": len(index_entries),
        "dates": [e['op_date'] for e in index_entries],
        "summaries": index_entries
    }
    
    # Write to public/data/history/history_index.json
    out_path = os.path.join(history_root, "history_index.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(history_index, f, ensure_ascii=False, indent=2)
    
    print(f"✅ history_index.json written: {len(index_entries)} dates")
    for e in index_entries:
        print(f"  {e['op_date']}: Forecast={e['forecast_total']:,} | Inbound={e['inbound_orders']:,}")

if __name__ == '__main__':
    build_history_index()
