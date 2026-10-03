# Dinh nghia hanh dong: chay file batch run_sync_receiving.bat
$TaskName = "Sync_Receiving_Report_1h"
$Action = New-ScheduledTaskAction -Execute "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync\run_sync_receiving.bat" -WorkingDirectory "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync"

# Dinh nghia thoi gian: Chay moi 1 tieng bat dau tu bay gio
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)

# Lay ten User hien tai de chay tac vu duoi quyen User nay
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Cau hinh settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

# Dang ky tac vu vao Windows Task Scheduler
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -User $User -Settings $Settings -Force

Write-Host "Register task $TaskName success! Runs every 1 hour indefinitely." -ForegroundColor Green
