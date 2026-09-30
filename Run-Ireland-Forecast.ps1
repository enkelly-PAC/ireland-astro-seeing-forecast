$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $Root "src"

& python -c "import astronomy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing forecast tool dependencies..."
    & python -m pip install -e $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the forecast tool dependencies."
    }
}

$HostName = "127.0.0.1"
$Port = 8765
$Url = "http://$($HostName):$($Port)/"

Write-Host "Starting the British Isles astronomy forecast server on $Url"

$serverProcess = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "meteoblue_seeing", "serve", "--host", $HostName, "--port", $Port) `
    -NoNewWindow -PassThru

try {
    $ready = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        if ($serverProcess.HasExited) {
            throw "Forecast server exited before becoming ready."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $ready) {
        throw "Forecast server did not become ready within 30 seconds."
    }

    Write-Host "Forecast tool is ready. Opening $Url"
    Start-Process $Url
    Wait-Process -Id $serverProcess.Id
}
finally {
    if (-not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
}
