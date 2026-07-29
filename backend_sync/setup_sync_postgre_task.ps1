# Định nghĩa hành động: chạy file batch run_sync_postgre.bat
$TaskName = "Sync_Postgre_30m"
$Action = New-ScheduledTaskAction -Execute "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync\run_sync_postgre.bat" -WorkingDirectory "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync"

# Định nghĩa thời gian: Chạy mỗi 30 phút bắt đầu từ bây giờ
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)

# Lấy tên User hiện tại để chạy tác vụ dưới quyền User này
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Cấu hình settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

# Đăng ký tác vụ vào Windows Task Scheduler
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -User $User -Settings $Settings -Force

Write-Host "Register task $TaskName success!" -ForegroundColor Green
