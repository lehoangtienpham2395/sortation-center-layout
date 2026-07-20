"""
auto_sync_schedule.py — Chạy theo lịch Windows Task Scheduler mỗi 30 phút.
- Pull Git để lấy DB mới nhất từ GitHub (nếu có ai đó push trước)
- Chạy sync_to_sheets.py để kéo data từ JFS API
- Commit & push SQLite DB + JSON lên GitHub
"""
import os, sys, subprocess, shutil
from datetime import datetime
from zoneinfo import ZoneInfo
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

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

    # 1. Pull Git để lấy code/config mới nhất từ GitHub
    log("📥 [1/4] Pull code/config mới nhất từ GitHub...")
    # Dọn dẹp các thay đổi của file data JSON cục bộ để tránh xung đột khi pull
    subprocess.run(["git", "checkout", "--", "data/", "src/data/"], cwd=BASE_DIR, capture_output=True)
    run(["git", "pull", "--rebase", "origin", "main"], timeout=30)

    # 2. Chạy sync chính (kéo JFS API → SQLite → JSON)
    python_exe = sys.executable
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        python_exe = venv_py

    sync_script = os.path.join(BASE_DIR, "backend_sync", "sync_to_sheets.py")
    log("🚀 [2/4] Chạy sync script (real-time stream)...")
    try:
        p = subprocess.Popen(
            [python_exe, "-u", sync_script, "--sync-only"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )
        
        stdout_lines = []
        # Đọc trực tiếp và in ra console theo thời gian thực
        while True:
            line = p.stdout.readline()
            if not line and p.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                stdout_lines.append(line.strip())
        
        p.wait(timeout=1200)
        
        if p.returncode == 0:
            log("✅ Sync hoàn tất.")
        else:
            log(f"⚠️ Sync exit code: {p.returncode}")
        
        # Ghi 10 dòng cuối vào file log
        log("📋 Nhật ký 10 dòng cuối của sync script:")
        for l in stdout_lines[-10:]:
            if l.strip(): log(f"     {l}")
    except subprocess.TimeoutExpired:
        log("❌ Sync timeout sau 20 phút!")
        if 'p' in locals():
            p.kill()
        return
    except Exception as e:
        log(f"❌ Lỗi chạy sync: {e}")
        return

    # 3. Commit & push DB + JSON lên GitHub
    log("☁️  [3/4] Commit & push lên GitHub...")
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
         "data/latest.json.gz",
         "src/data/inventory.json",
         "src/data/inbound.json",
         "src/data/outbound.json",
         "src/data/backlog.json",
         "src/data/arrival.json",
         "src/data/linehaul.json",
         "src/data/truck_eta.json",
         "src/data/config.json",
         "src/data/last_update.json",
         "src/data/heatmap.json",
         "src/data/latest.json.gz",
         "backend_sync/config/valid.csv"])

    # Kiểm tra có thay đổi không
    r_status = subprocess.run(["git", "diff", "--staged", "--quiet"],
                               cwd=BASE_DIR, capture_output=True)
    if r_status.returncode == 0:
        log("✅ [3/4] Không có thay đổi mới — bỏ qua commit.")
    else:
        # Stash any remaining unstaged changes to avoid rebase conflict
        subprocess.run(["git", "stash", "--include-untracked", "-m", "auto-stash before pull"],
                       cwd=BASE_DIR, capture_output=True)
        run(["git", "pull", "--rebase", "origin", "main"], timeout=30)
        # Restore stashed changes (ignore errors if nothing stashed)
        subprocess.run(["git", "stash", "pop"], cwd=BASE_DIR, capture_output=True)
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
