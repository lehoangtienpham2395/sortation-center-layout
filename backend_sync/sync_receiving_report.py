import os
import sys
import json
import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
KPI_HUB_DIR = os.path.abspath("C:/Users/lehoa/.gemini/antigravity/scratch/kpi-hub")

if KPI_HUB_DIR not in sys.path:
    sys.path.insert(0, KPI_HUB_DIR)

def sync_receiving_table():
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] Syncing Inbound Receiving Table...")
    table_data = None
    try:
        from forecast_engine import get_inbound_receiving_table
        table_data = get_inbound_receiving_table()
    except Exception as e:
        print(f"   Warning from forecast_engine: {e}")
        cache_path = os.path.join(KPI_HUB_DIR, "forecast_day_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    table_data = c.get("inbound_receiving_table")
            except Exception as _ce:
                print(f"   Could not load cache: {_ce}")

    if not table_data or not table_data.get("grand_total"):
        print("   Failed: Could not obtain inbound receiving table data")
        return False

    targets = [
        os.path.join(PARENT_DIR, "data", "inbound_receiving_table.json"),
        os.path.join(PARENT_DIR, "public", "data", "inbound_receiving_table.json"),
        os.path.join(PARENT_DIR, "src", "data", "inbound_receiving_table.json")
    ]

    for p in targets:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(table_data, f, ensure_ascii=False, indent=2)
        print(f"   [OK] Saved: {p}")

    print(f"Inbound Receiving Table updated successfully at {table_data.get('updated_at')}")
    return True

if __name__ == "__main__":
    success = sync_receiving_table()
    if success and "--push" in sys.argv:
        import subprocess
        try:
            print("Committing and pushing to git...")
            subprocess.run(["git", "add", "data/inbound_receiving_table.json", "src/data/inbound_receiving_table.json", "public/data/inbound_receiving_table.json"], cwd=PARENT_DIR, check=True)
            subprocess.run(["git", "commit", "-m", f"chore(receiving): auto-sync inbound receiving report [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}]"], cwd=PARENT_DIR, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=PARENT_DIR, check=True)
            print("Git push complete.")
        except Exception as e:
            print(f"Git error: {e}")
