$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run the README installation commands first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination (Join-Path $PSScriptRoot '.env') }
Push-Location $PSScriptRoot
try {
    $taskListeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($taskListeners) { throw 'Port 8000 is already in use. Open the existing app or stop that service first.' }
    & $taskPython -m app.cli migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    $taskWeb = Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--log-level','warning') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    $taskWorker = Start-Process -FilePath $taskPython -ArgumentList @('-m','app.worker') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    @{ web = $taskWeb.Id; worker = $taskWorker.Id; created = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot '.local-processes.json')
    Write-Output 'Pool Headcount started at http://localhost:8000. Use pause in the app before stopping.'
} finally { Pop-Location }
