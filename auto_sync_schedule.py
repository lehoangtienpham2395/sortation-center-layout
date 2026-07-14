"""
auto_sync_schedule.py — Chạy theo lịch Windows Task Scheduler mỗi 30 phút.
- Pull Git để lấy DB mới nhất từ GitHub (nếu có ai đó push trước)
- Chạy sync_to_sheets.py để kéo data từ JFS API
- Commit & push SQLite DB + JSON lên GitHub
"""
import os, sys, subprocess, shutil
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "backend_sync", "db", "auto_sync.log")
TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')

def log(msg):
    ts = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, cwd=BASE_DIR, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)
        if r.stdout.strip():
            log(f"  → {r.stdout.strip()[:200]}")
        if r.returncode != 0 and r.stderr.strip():
            log(f"  ⚠️ {r.stderr.strip()[:200]}")
        return r.returncode == 0
    except Exception as e:
        log(f"  ❌ Lỗi: {e}")
        return False

def main():
    log("=" * 55)
    log("🔄 Bắt đầu Auto Sync (30-min schedule)")

    # 1. Pull Git để lấy DB mới nhất từ GitHub
    log("📥 [1/4] Pull DB mới nhất từ GitHub...")
    run(["git", "fetch", "origin"])
    run(["git", "checkout", "origin/main", "--",
         "backend_sync/db/state.db"], timeout=30)

    # 2. Chạy sync chính (kéo JFS API → SQLite → JSON)
    python_exe = sys.executable
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        python_exe = venv_py

    sync_script = os.path.join(BASE_DIR, "backend_sync", "sync_to_sheets.py")
    log("🚀 [2/4] Chạy sync script...")
    try:
        r = subprocess.run(
            [python_exe, sync_script, "--sync-only"],
            cwd=BASE_DIR,
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=1200  # 20 phút
        )
        if r.returncode == 0:
            log("✅ Sync hoàn tất.")
        else:
            log(f"⚠️ Sync exit code: {r.returncode}")
        # Log 10 dòng cuối output
        lines = (r.stdout or '').strip().split('\n')
        for l in lines[-10:]:
            if l.strip(): log(f"     {l}")
    except subprocess.TimeoutExpired:
        log("❌ Sync timeout sau 20 phút!")
        return
    except Exception as e:
        log(f"❌ Lỗi chạy sync: {e}")
        return

    # 3. Commit & push DB + JSON lên GitHub
    log("☁️  [3/4] Commit & push lên GitHub...")
    ts_str = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M')

    run(["git", "add",
         "backend_sync/db/state.db",
         "data/inventory.json",
         "data/inbound.json",
         "data/outbound.json",
         "data/backlog.json",
         "data/arrival.json",
         "data/linehaul.json",
         "data/config.json",
         "src/data/config.json",
         "backend_sync/config/valid.csv"])

    # Kiểm tra có thay đổi không
    r_status = subprocess.run(["git", "diff", "--staged", "--quiet"],
                               cwd=BASE_DIR, capture_output=True)
    if r_status.returncode == 0:
        log("✅ [3/4] Không có thay đổi mới — bỏ qua commit.")
    else:
        run(["git", "pull", "--rebase", "origin", "main"], timeout=30)
        run(["git", "commit", "-m",
             f"chore(data): auto-sync {ts_str} ICT [skip ci]"])
        ok = run(["git", "push", "origin", "main"], timeout=60)
        if ok:
            log("✅ [3/4] Push thành công!")
        else:
            log("⚠️ [3/4] Push thất bại — sẽ thử lại lần sau.")

    log("✅ [4/4] Hoàn tất Auto Sync!")
    log("=" * 55)

if __name__ == "__main__":
    main()
