$ErrorActionPreference = 'Stop'
$taskFile = Join-Path $PSScriptRoot '.local-processes.json'
if (-not (Test-Path -LiteralPath $taskFile)) { throw 'No processes recorded by start.ps1.' }
$taskRecord = Get-Content -LiteralPath $taskFile -Raw | ConvertFrom-Json
$taskCreated = [datetime]::Parse($taskRecord.created)
foreach ($taskPid in @($taskRecord.web, $taskRecord.worker)) {
    $taskProcess = Get-Process -Id $taskPid -ErrorAction SilentlyContinue
    if ($taskProcess -and $taskProcess.ProcessName -eq 'python' -and [math]::Abs(($taskProcess.StartTime - $taskCreated).TotalSeconds) -lt 30) {
        & taskkill /PID $taskPid /T /F | Out-Null
    }
}
Remove-Item -LiteralPath $taskFile
Write-Output 'Local processes stopped. Durable checkpoints remain in data.'
