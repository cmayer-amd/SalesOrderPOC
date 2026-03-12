param(
    [int]$Port = 8000,
    [string]$HostAddress = "0.0.0.0",
    [string]$PythonPath = "C:\Users\cmayer\AppData\Local\Programs\Python\Python312\python.exe",
    [switch]$NoAccessLog,
    [string]$LogLevel = "warning"
)

$ErrorActionPreference = "Stop"

try {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    Set-Location $projectRoot

    # Stop any app currently listening on target port.
    $listenerPid = (
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess
    )
    if ($listenerPid) {
        Stop-Process -Id $listenerPid -Force
        Start-Sleep -Milliseconds 400
    }

    if (-not (Test-Path $PythonPath)) {
        throw "Python executable not found at '$PythonPath'."
    }

    $uvicornArgs = @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", $HostAddress,
        "--port", "$Port",
        "--log-level", $LogLevel
    )
    if ($NoAccessLog) {
        $uvicornArgs += "--no-access-log"
    }

    # Start in a detached process so the app survives this script process.
    Start-Process -FilePath $PythonPath -ArgumentList $uvicornArgs -WorkingDirectory $projectRoot | Out-Null

    Start-Sleep -Seconds 1
    $status = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing).StatusCode
    Write-Host "App restarted successfully on http://127.0.0.1:$Port (HTTP $status)."
}
catch {
    Write-Host "ERROR:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
