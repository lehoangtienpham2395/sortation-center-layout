"""
startup_sync.py — Tự động chạy khi bro mở máy.
Kiểm tra khoảng cách lần sync cuối → nếu máy đã tắt > 30 phút thì chạy backfill.
Đăng ký qua Windows Task Scheduler: chạy khi user logon.
"""
import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SYNC_SCRIPT   = os.path.join(BASE_DIR, "backend_sync", "sync_to_sheets.py")
LAST_RUN_FILE = os.path.join(BASE_DIR, "backend_sync", "db", "last_run.txt")
LOG_FILE      = os.path.join(BASE_DIR, "backend_sync", "db", "startup_sync.log")

TZ_VN             = ZoneInfo('Asia/Ho_Chi_Minh')
GAP_THRESHOLD_MIN = 30   # Nếu máy tắt > 30 phút thì backfill
MAX_BACKFILL_DAYS = 5    # Tối đa backfill 5 ngày

# ──────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────
# ĐỌC THỜI GIAN SYNC CUỐI
# ──────────────────────────────────────────────────────────────
def get_last_run() -> datetime | None:
    # Ưu tiên đọc từ last_run.txt
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, "r") as f:
                val = f.read().strip()
            if val:
                return datetime.strptime(val, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_VN)
        except Exception:
            pass

    # Fallback: đọc last_updated mới nhất trong SQLite
    db_file = os.path.join(BASE_DIR, "backend_sync", "db", "state.db")
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            c    = conn.cursor()
            c.execute("SELECT MAX(last_updated) FROM shipments")
            row = c.fetchone()
            conn.close()
            if row and row[0]:
                return datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_VN)
        except Exception:
            pass

    return None

# ──────────────────────────────────────────────────────────────
# TÍNH KHOẢNG GAP & SỐ NGÀY BACKFILL CẦN THIẾT
# ──────────────────────────────────────────────────────────────
def calc_backfill_days(last_run: datetime, now: datetime) -> int:
    gap_minutes = (now - last_run).total_seconds() / 60
    if gap_minutes < GAP_THRESHOLD_MIN:
        return 0
    gap_days = max(1, int((now - last_run).days) + 1)
    return min(gap_days, MAX_BACKFILL_DAYS)

# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
def main():
    now = datetime.now(TZ_VN)
    log("=" * 60)
    log(f"🚀 Startup Sync khởi động: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    last_run = get_last_run()
    if last_run:
        gap_min = (now - last_run).total_seconds() / 60
        log(f"📅 Lần sync cuối: {last_run.strftime('%Y-%m-%d %H:%M:%S')} | Gap: {gap_min:.0f} phút")
    else:
        gap_min = 999
        log("⚠️ Không tìm thấy thời gian sync cuối — giả định máy đã tắt lâu.")

    backfill_days = calc_backfill_days(last_run, now) if last_run else MAX_BACKFILL_DAYS

    if backfill_days == 0:
        log(f"✅ Gap < {GAP_THRESHOLD_MIN} phút — không cần backfill. Thoát.")
        return

    log(f"⏳ Gap lớn hơn ngưỡng → Cần backfill {backfill_days} ngày.")
    log(f"🔄 Đang chạy sync script: {SYNC_SCRIPT}")

    # Xác định Python executable (ưu tiên venv cùng thư mục)
    python_exe = sys.executable
    venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
        python_exe = venv_python

    cmd = [
        python_exe,
        SYNC_SCRIPT,
        "--sync-only",
        f"--days-back={backfill_days}"
    ]

    log(f"   CMD: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800  # 30 phút timeout
        )
        if result.returncode == 0:
            log(f"✅ Sync hoàn tất thành công (return code 0).")
        else:
            log(f"⚠️ Sync kết thúc với return code {result.returncode}.")

        # Ghi log chi tiết của sync script vào log file
        if result.stdout:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n--- SYNC OUTPUT ---\n")
                f.write(result.stdout[-5000:])  # Giới hạn 5000 ký tự cuối
                f.write("\n--- END SYNC OUTPUT ---\n")
        if result.stderr:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n--- SYNC STDERR ---\n")
                f.write(result.stderr[-2000:])
                f.write("\n---\n")

    except subprocess.TimeoutExpired:
        log("❌ Sync timeout sau 30 phút!")
    except Exception as e:
        log(f"❌ Lỗi chạy sync script: {e}")

    log("=" * 60)


if __name__ == "__main__":
    main()
