$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $Root "src"
$Output = Join-Path $Root "reports"

python -m meteoblue_seeing wicklow-forecast --hours 96 --output-directory $Output
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
