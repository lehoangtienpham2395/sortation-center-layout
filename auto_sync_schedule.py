"""
auto_sync_schedule.py — Scheduled 30-min Auto Sync Execution
===========================================================
1. Safe pull (git pull --rebase, NO git reset --hard, NO git clean)
2. Lock file handling (sync.lock) to prevent duplicate runs
3. Run sync_postgre.py (PostgreSQL → Dashboard JSONs + JFS API Linehaul/Truck_ETA)
4. Safe git add, commit & push data files to GitHub
"""
import os
import sys
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
LOG_FILE  = os.path.join(BASE_DIR, "backend_sync", "db", "auto_sync.log")
LOCK_FILE = os.path.join(BASE_DIR, "sync.lock")
TZ_VN     = ZoneInfo('Asia/Ho_Chi_Minh')


def log(msg: str):
    ts = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, cwd=BASE_DIR, timeout=60):
    try:
        r = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout
        )
        if r.stdout.strip():
            log(f"  → {r.stdout.strip()[:200]}")
        if r.returncode != 0 and r.stderr.strip():
            log(f"  ⚠️ {r.stderr.strip()[:200]}")
        return r.returncode == 0
    except Exception as e:
        log(f"  ❌ Error executing command {cmd}: {e}")
        return False


def main():
    log("=" * 55)
    log("🔄 Starting Auto Sync Pipeline (30-min schedule)")

    # Lock file protection
    if os.path.exists(LOCK_FILE):
        file_age = time.time() - os.path.getmtime(LOCK_FILE)
        if file_age < 1200:  # < 20 minutes
            log(f"⚠️ Lock file exists ({int(file_age)}s old). Another sync is running. Aborting.")
            return
        else:
            log(f"⚠️ Removing stale lock file ({int(file_age)}s old).")
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass

    # Create lock file
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log(f"⚠️ Cannot create lock file: {e}")

    try:
        # 1. Safe pull latest code/config (NO git reset --hard!)
        log("📥 [1/4] Pulling latest code/config from GitHub (git pull --rebase)...")
        run(["git", "pull", "--rebase", "origin", "main"], timeout=30)

        # 2. Run sync_postgre.py
        python_exe = sys.executable
        venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_py):
            python_exe = venv_py

        sync_script = os.path.join(BASE_DIR, "backend_sync", "sync_postgre.py")
        log(f"🚀 [2/4] Running sync_postgre.py ({python_exe})...")

        try:
            p = subprocess.Popen(
                [python_exe, "-u", sync_script],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            stdout_lines = []
            while True:
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    stdout_lines.append(line.strip())

            p.wait(timeout=600)

            if p.returncode == 0:
                log("✅ Sync engine completed successfully.")
            else:
                log(f"⚠️ Sync engine exit code: {p.returncode}")

            log("📋 Last 10 lines of sync engine log:")
            for l in stdout_lines[-10:]:
                if l.strip():
                    log(f"     {l}")

        except subprocess.TimeoutExpired:
            log("❌ Sync engine timed out after 10 minutes!")
            if 'p' in locals():
                p.kill()
            return
        except Exception as e:
            log(f"❌ Error running sync engine: {e}")
            return

        # 3. Safe commit & push JSONs
        log("☁️  [3/4] Commit & push updated JSONs to GitHub...")
        ts_str = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M')

        run(["git", "add",
             "data/inventory.json",
             "data/inbound.json",
             "data/outbound.json",
             "data/backlog.json",
             "data/arrival.json",
             "data/linehaul.json",
             "data/truck_eta.json",
             "data/config.json",
             "data/last_update.json",
             "data/heatmap.json",
             "data/hub_inventory_pivot.json",
             "data/latest.json.gz",
             "backend_sync/config/valid.csv"])

        r_status = subprocess.run(["git", "diff", "--staged", "--quiet"],
                                   cwd=BASE_DIR, capture_output=True)
        if r_status.returncode == 0:
            log("✅ [3/4] No data changes detected — skipping commit.")
        else:
            run(["git", "commit", "-m", f"chore(data): auto-sync {ts_str} ICT"])
            run(["git", "pull", "--rebase", "origin", "main"], timeout=30)
            ok = run(["git", "push", "origin", "main"], timeout=60)
            if ok:
                log("✅ [3/4] Push successful!")
            else:
                log("⚠️ [3/4] Push failed — will retry next cycle.")

        log("✅ [4/4] Auto Sync completed successfully!")
        log("=" * 55)

    finally:
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass


if __name__ == "__main__":
    main()
