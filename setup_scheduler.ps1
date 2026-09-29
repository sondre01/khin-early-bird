# Khin Early Bird - Windows Task Scheduler Setup
# Registers a daily background task to execute run_pipeline.py every morning

param (
    [string]$Time = "08:00"
)

$TaskName = "KhinEarlyBirdDailyJobHunt"
$PythonPath = (Get-Command python).Source
$ScriptPath = Join-Path $PSScriptRoot "run_pipeline.py"
$WorkingDirectory = $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  🦅 Setting up Khin Early Bird Daily Schedule" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Task Name:        $TaskName"
Write-Host "Daily Run Time:   $Time AM"
Write-Host "Python:           $PythonPath"
Write-Host "Working Dir:      $WorkingDirectory"
Write-Host "Target Script:    $ScriptPath"

# Action to run
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory $WorkingDirectory

# Daily Trigger
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

# Settings (WakeToRun, Don't stop if battery, Run with highest available privileges)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Unregister if already exists
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Register task
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily automated job extraction and AI qualification matching for Khin Andrei Gamboa" | Out-Null
    Write-Host "`n✅ Successfully registered Windows Scheduled Task: '$TaskName'!" -ForegroundColor Green
    Write-Host "   The pipeline will run automatically every day at $Time." -ForegroundColor Green
    Write-Host "   To test running it now via Task Scheduler, run:" -ForegroundColor Yellow
    Write-Host "   Start-ScheduledTask -TaskName '$TaskName'`n" -ForegroundColor Yellow
} catch {
    Write-Host "`n⚠️ Note: Administrative privileges may be required to register tasks." -ForegroundColor Yellow
    Write-Host "   Error: $_" -ForegroundColor Red
}
