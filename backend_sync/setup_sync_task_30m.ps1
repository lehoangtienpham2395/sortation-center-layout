# Dinh nghia hanh dong: chay file batch run_sync.bat
$Action = New-ScheduledTaskAction -Execute "C:\Users\lehoa\OneDrive\Desktop\testing\run_sync.bat"

# Dinh nghia thoi gian: Chay moi 30 phut mai mai (indefinitely) bat dau tu bay gio
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)

# Lay ten User hien tai de chay tac vu duoi quyen User nay
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Cau hinh settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances Parallel

# Dang ky tac vu vao Windows Task Scheduler
Register-ScheduledTask -TaskName "JTCargo_Sheets_Sync_30m" -Action $Action -Trigger $Trigger -User $User -Settings $Settings -Force

Write-Host "Register task JTCargo_Sheets_Sync_30m success!" -ForegroundColor Green
