import subprocess
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Checking and terminating any background Python sync daemons via PowerShell...")

ps_cmd = "Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe'} | Select-Object ProcessId, CommandLine | ConvertTo-Json"

try:
    res = subprocess.check_output(f"powershell -ExecutionPolicy Bypass -Command \"{ps_cmd}\"", shell=True, text=True)
    import json
    data = json.loads(res)
    if isinstance(data, dict):
        data = [data]
        
    killed = 0
    for p in data:
        pid = p.get('ProcessId')
        cmd = p.get('CommandLine') or ''
        if pid and int(pid) != os.getpid():
            if 'pipeline' in cmd or 'sync' in cmd or 'realtime' in cmd or 'etl' in cmd or 'run_etl' in cmd:
                print(f"Stopping background daemon PID {pid}: {cmd[:100]}...")
                subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                killed += 1
                
    print(f"\n✅ Total {killed} background sync daemons stopped!")
except Exception as e:
    print(f"Result: {e}")
