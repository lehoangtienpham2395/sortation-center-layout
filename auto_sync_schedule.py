"""
auto_sync_schedule.py — Chạy theo lịch Windows Task Scheduler mỗi 30 phút.

Luồng (v2 — đã chuyển sang PostgreSQL):
  1. Git pull --rebase (KHÔNG reset --hard / clean để tránh mất file local chưa commit)
  2. Dọn sync.lock nếu stale (>30 phút) hoặc rỗng
  3. Chạy backend_sync/sync_postgre.py
       → đọc enriched.dispatch_enriched (PG) → xuất 9 JSON vào data/
  4. Nếu sync THÀNH CÔNG → git add data/*.json + commit + push origin main
     Nếu sync THẤT BẠI → KHÔNG push JSON cũ, chỉ log lỗi rõ ràng
  5. GitHub Actions deploy.yml (đã có) sẽ build & deploy Pages khi nhận push
"""
import os, sys, subprocess, time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "backend_sync", "db", "auto_sync.log")
LOCK_FILE = os.path.join(BASE_DIR, "backend_sync", "sync.lock")
TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')

# JSON files mà sync_postgre.py xuất ra (đẩy lên GitHub sau mỗi lần sync)
DATA_JSON_FILES = [
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
]

SYNC_TIMEOUT_SEC = 1200  # 20 phút


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


def cleanup_stale_lock():
    """Xoá sync.lock nếu rỗng hoặc cũ hơn 30 phút (coi như crash cũ)."""
    if not os.path.exists(LOCK_FILE):
        return
    age_min = (time.time() - os.path.getmtime(LOCK_FILE)) / 60
    size = os.path.getsize(LOCK_FILE)
    if size == 0 or age_min > 30:
        try:
            os.remove(LOCK_FILE)
            log(f"🧹 Đã xoá sync.lock (size={size}B, age={age_min:.1f}min)")
        except Exception as e:
            log(f"⚠️ Không xoá được sync.lock: {e}")
    else:
        log(f"🔒 sync.lock còn hợp lệ (age={age_min:.1f}min) — có sync khác đang chạy?")


def acquire_lock():
    """Tạo lock file. Trả về True nếu acquire được, False nếu đã có tiến trình khác."""
    if os.path.exists(LOCK_FILE):
        age_min = (time.time() - os.path.getmtime(LOCK_FILE)) / 60
        if age_min < 30:
            return False  # có tiến trình khác đang chạy
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return True


def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


def run_sync():
    """Chạy sync_postgre.py. Trả về True nếu THÀNH CÔNG (exit code 0)."""
    python_exe = sys.executable
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        python_exe = venv_py

    sync_script = os.path.join(BASE_DIR, "backend_sync", "sync_postgre.py")
    log(f"🚀 [2/4] Chạy sync_postgre.py (đọc PG → xuất JSON)...")
    try:
        p = subprocess.Popen(
            [python_exe, "-u", sync_script],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1
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
        p.wait(timeout=SYNC_TIMEOUT_SEC)

        if p.returncode == 0:
            log("✅ Sync hoàn tất (exit 0).")
            return True
        else:
            log(f"❌ Sync THẤT BẠI (exit code {p.returncode}). KHÔNG push JSON cũ.")
            log("📋 Nhật ký 10 dòng cuối của sync script:")
            for l in stdout_lines[-10:]:
                if l.strip():
                    log(f"     {l}")
            return False
    except subprocess.TimeoutExpired:
        log(f"❌ Sync timeout sau {SYNC_TIMEOUT_SEC}s!")
        if 'p' in locals():
            p.kill()
        return False
    except Exception as e:
        log(f"❌ Lỗi chạy sync: {e}")
        return False


def git_push_json(ts_str):
    """Commit & push data/*.json lên GitHub. Trả về True nếu push thành công."""
    log("☁️  [3/4] Commit & push JSON lên GitHub...")
    # git add danh sách file (bỏ qua file không tồn tại)
    existing = [f for f in DATA_JSON_FILES if os.path.exists(os.path.join(BASE_DIR, f))]
    if not existing:
        log("⚠️ Không có file JSON nào tồn tại để commit.")
        return False
    run(["git", "add"] + existing)

    # Kiểm tra có thay đổi staged không
    r_status = subprocess.run(["git", "diff", "--staged", "--quiet"],
                              cwd=BASE_DIR, capture_output=True)
    if r_status.returncode == 0:
        log("✅ [3/4] Không có thay đổi mới — bỏ qua commit.")
        return True  # vẫn coi là OK (không có gì để push)

    run(["git", "commit", "-m", f"chore(data): auto-sync {ts_str} ICT (from PG)"])
    run(["git", "pull", "--rebase", "origin", "main"], timeout=30)
    ok = run(["git", "push", "origin", "main"], timeout=60)
    if ok:
        log("✅ [3/4] Push thành công!")
    else:
        log("⚠️ [3/4] Push thất bại — sẽ thử lại lần sau.")
    return ok


def main():
    log("=" * 55)
    log("🔄 Bắt đầu Auto Sync v2 (30-min schedule, PG engine)")

    # 0. Lock & dọn stale lock
    cleanup_stale_lock()
    if not acquire_lock():
        log("⏭️  Có sync khác đang chạy — thoát.")
        log("=" * 55)
        return

    try:
        # 1. Pull Git (KHÔNG reset --hard, KHÔNG clean)
        log("📥 [1/4] Pull code/config mới nhất từ GitHub...")
        run(["git", "pull", "--rebase", "origin", "main"], timeout=30)

        # 2. Chạy sync
        sync_ok = run_sync()
        if not sync_ok:
            log("⛔ [3/4] BỎ QUA commit/push vì sync thất bại.")
            log("✅ [4/4] Auto Sync kết thúc (có lỗi).")
            log("=" * 55)
            return

        # 3. Commit & push JSON
        ts_str = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M')
        git_push_json(ts_str)

        log("✅ [4/4] Hoàn tất Auto Sync!")
    finally:
        release_lock()
    log("=" * 55)


if __name__ == "__main__":
    main()
