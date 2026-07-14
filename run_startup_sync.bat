@echo off
cd /d "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"
python startup_sync.py >> "backend_sync\db\startup_sync.log" 2>&1
