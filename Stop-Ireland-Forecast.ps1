$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".ireland-forecast-server.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No saved forecast server process was found."
    exit 0
}

$savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
if ($savedPid -notmatch "^\d+$") {
    Remove-Item $PidFile -Force
    throw "The saved forecast server process ID is invalid."
}

$process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
if ($process -and $process.CommandLine -match "meteoblue_seeing.+serve") {
    Stop-Process -Id ([int]$savedPid) -Force
    Write-Host "Ireland forecast server stopped."
}
else {
    Write-Host "The saved forecast server process is no longer running."
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
