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

    if (-not (Test-Path $PythonPath)) {
        throw "Python executable not found at '$PythonPath'."
    }

    $existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($existingListener) {
        Write-Host "Port $Port is already in use. Use scripts/restart-app.ps1 to replace it."
        exit 0
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

    Start-Process -FilePath $PythonPath -ArgumentList $uvicornArgs -WorkingDirectory $projectRoot | Out-Null

    Start-Sleep -Seconds 1
    $status = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing).StatusCode
    Write-Host "App started on http://127.0.0.1:$Port (HTTP $status)."
}
catch {
    Write-Host "ERROR:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
