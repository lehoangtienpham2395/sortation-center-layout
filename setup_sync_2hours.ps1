# setup_sync_2hours.ps1
# Dang ky Task chay 2 tieng / lan trong khung 11:00 toi 22:00 moi ngay

$taskName = 'JFS_Sync_2hours_11to22'
$batFile  = 'C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\sync_jfs_2hours.bat'
$workDir  = 'C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout'

# 1. Xoa task cu neu da ton tai
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 2. Action: Chay cmd.exe /c sync_jfs_2hours.bat
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$batFile`"" -WorkingDirectory $workDir

# 3. Triggers: 11:00, 13:00, 15:00, 17:00, 19:00, 21:00, 22:00
$times = @('11:00AM', '01:00PM', '03:00PM', '05:00PM', '07:00PM', '09:00PM', '10:00PM')
$triggers = foreach ($t in $times) {
    New-ScheduledTaskTrigger -Daily -At $t
}

# 4. Settings: wake PC, bat dau ngay neu bi lo hen, timeout 60 phut
$settings = New-ScheduledTaskSettingsSet `-WakeToRun `-ExecutionTimeLimit (New-TimeSpan -Minutes 60) `-StartWhenAvailable `-RunOnlyIfNetworkAvailable

# 5. Dang ky vao Windows Task Scheduler
$task = Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $triggers `
    -Settings    $settings `
    -RunLevel    Highest `
    -Description 'Tu dong dong bo luong JFS ETL 2tieng/lan khung 11:00 den 22:00 moi ngay' `
    -Force

if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    Write-Host '=== TASK DANG KY THANG CONG ===' -ForegroundColor Green
    Write-Host "Task Name : $($task.TaskName)"
    Write-Host "Next Run  : $($info.NextRunTime)"
    Write-Host "State     : $($task.State)"
    Write-Host ''
    Write-Host "Kiem tra : schtasks /query /tn `"$taskName`" /fo LIST"
    Write-Host "Chay thu : schtasks /run /tn `"$taskName€""
} else {
    Write-Host 'ERROR: Khong the dang ky task!' -ForegroundColor Red
}
