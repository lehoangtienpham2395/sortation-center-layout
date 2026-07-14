"""
pre_sleep_push.py — Chạy TRƯỚC khi máy sleep (Kernel-Power Event ID 42)
Mục tiêu: Push nhanh SQLite + JSON lên GitHub trong vòng ~30 giây
KHÔNG kéo API, chỉ lưu trạng thái hiện tại lên cloud
"""
import os, sys, subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "backend_sync", "db", "pre_sleep.log")
TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')

def log(msg):
    ts = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        out = (r.stdout or '').strip()
        if out:
            log(f"  → {out[:150]}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"  ⚠️ Timeout: {' '.join(cmd)}")
        return False
    except Exception as e:
        log(f"  ❌ {e}")
        return False

def main():
    log("=" * 50)
    log("🌙 Pre-Sleep Push: lưu trạng thái lên GitHub")

    ts_str = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M')

    # Stage các file cần thiết
    files_to_stage = [
        "backend_sync/db/state.db",
        "data/inventory.json",
        "data/inbound.json",
        "data/outbound.json",
        "data/backlog.json",
        "data/arrival.json",
        "data/linehaul.json",
        "data/config.json",
        "src/data/config.json",
    ]
    run(["git", "add"] + files_to_stage)

    # Kiểm tra có thay đổi không
    r = subprocess.run(["git", "diff", "--staged", "--quiet"],
                       cwd=BASE_DIR, capture_output=True)
    if r.returncode == 0:
        log("✅ Không có thay đổi — bỏ qua commit.")
        log("=" * 50)
        return

    # Commit và push nhanh (timeout 25 giây)
    run(["git", "commit", "-m",
         f"chore(pre-sleep): save state before sleep {ts_str} ICT [skip ci]"], timeout=15)

    ok = run(["git", "push", "origin", "main"], timeout=25)
    if ok:
        log("✅ Push thành công — máy có thể ngủ an toàn!")
    else:
        # Thử force push nếu có conflict
        log("⚠️ Push thất bại, thử force...")
        run(["git", "fetch", "origin"], timeout=15)
        run(["git", "push", "origin", "main", "--force-with-lease"], timeout=25)

    log("🌙 Xong! Máy có thể sleep.")
    log("=" * 50)

if __name__ == "__main__":
    main()
