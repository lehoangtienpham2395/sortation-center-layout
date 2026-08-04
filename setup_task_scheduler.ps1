# setup_task_scheduler.ps1
# Chay script nay 1 lan de dang ky SnapshotDaily vao Windows Task Scheduler

$taskName  = "SnapshotDaily_0605AM"
$batFile   = "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\snapshot_daily.bat"
$workDir   = "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout"

# Xoa task cu neu ton tai
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Old task removed (if existed)."

# Action: chay cmd /c snapshot_daily.bat
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batFile`"" `
    -WorkingDirectory $workDir

# Trigger: 06:05 AM moi ngay
$trigger = New-ScheduledTaskTrigger -Daily -At "06:05AM"

# Settings: wake PC, bat dau ngay ca khi lo hen (StartWhenAvailable), timeout 60 phut
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Dang ky
$task = Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -RunLevel    Highest `
    -Description "Dong bang du lieu Inbound ngay hom qua vao lich su luc 06:05 AM moi ngay" `
    -Force

if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    Write-Host ""
    Write-Host "=== TASK SCHEDULER CONFIGURED SUCCESSFULLY ==="
    Write-Host "Task Name : $($task.TaskName)"
    Write-Host "Next Run  : $($info.NextRunTime)"
    Write-Host "State     : $($task.State)"
    Write-Host ""
    Write-Host "De kiem tra: schtasks /query /tn `"$taskName`" /fo LIST"
    Write-Host "De chay thu: schtasks /run /tn `"$taskName`""
} else {
    Write-Host "ERROR: Task creation failed!"
}
