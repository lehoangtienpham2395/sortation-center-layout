"""
DAEMON SYNC V2 -- Micro-Polling Loop (30 Seconds Interval)
Executes realtime delta sync in background and notifies Live Server.
"""

import sys
import os
import time
import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from pipeline_v2_realtime import run_realtime_delta_sync

INTERVAL_SECONDS = 30

def start_daemon():
    print(f"🚀 [VER 2 DAEMON] Starting Realtime Micro-Polling Daemon (Interval: {INTERVAL_SECONDS}s)...")
    print("Press Ctrl+C to stop.")
    
    cycle = 1
    while True:
        try:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n--- [Cycle #{cycle}] {now_str} ---")
            
            success, count = run_realtime_delta_sync(minutes_back=15)
            
            cycle += 1
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped by user.")
            break
        except Exception as e:
            print(f"❌ Daemon error in cycle #{cycle}: {e}")
        
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    start_daemon()
