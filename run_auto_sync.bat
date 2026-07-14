@echo off
cd /d "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"
python auto_sync_schedule.py >> "backend_sync\db\auto_sync.log" 2>&1
