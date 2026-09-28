$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostName = "127.0.0.1"
$Port = 8765
$Url = "http://$($HostName):$($Port)/"
$HealthUrl = "http://$($HostName):$($Port)/api/health"
$PidFile = Join-Path $Root ".ireland-forecast-server.pid"
$Reports = Join-Path $Root "reports"
$StdoutLog = Join-Path $Reports "ireland-forecast-server.log"
$StderrLog = Join-Path $Reports "ireland-forecast-server-error.log"

New-Item -ItemType Directory -Force -Path $Reports | Out-Null

& python -c "import astronomy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing forecast tool dependencies..."
    & python -m pip install -e $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the forecast tool dependencies."
    }
}

function Test-ForecastServer {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

if (Test-ForecastServer) {
    Write-Host "Forecast server is already running. Opening $Url"
    Start-Process $Url
    exit 0
}

if (Test-Path $PidFile) {
    $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($savedPid -match "^\d+$") {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -match "meteoblue_seeing.+serve") {
            Stop-Process -Id ([int]$savedPid) -Force
            Start-Sleep -Milliseconds 500
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$env:PYTHONPATH = Join-Path $Root "src"
$serverProcess = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "meteoblue_seeing", "serve", "--host", $HostName, "--port", $Port) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $serverProcess.Id -Encoding ascii

for ($attempt = 1; $attempt -le 60; $attempt++) {
    if ($serverProcess.HasExited) {
        $details = ""
        if (Test-Path $StderrLog) {
            $details = (Get-Content $StderrLog -Raw).Trim()
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        throw "Forecast server exited before becoming ready. $details"
    }
    if (Test-ForecastServer) {
        Write-Host "Forecast tool is ready. Opening $Url"
        Write-Host "It will keep running after this window closes."
        Write-Host "Use Stop-Ireland-Forecast.cmd when finished."
        Start-Process $Url
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
throw "Forecast server did not become ready within 30 seconds. Check $StderrLog"
