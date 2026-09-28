[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [string]$Location = "northeurope",
    [string]$ResourceGroup = "rg-ireland-astro-seeing",
    [string]$FunctionAppName = "ireland-astro-seeing-api-enkelly",
    [string]$PagesOrigin = "https://enkelly-pac.github.io"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$CorporateTenantId = "72f988bf-86f1-41af-91ab-2d7cd011db47"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI is required. Install it, then run az login with your personal account."
}

az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) {
    throw "The requested subscription is not available. Run az login with your personal account first."
}

$Account = az account show --output json | ConvertFrom-Json
if ($Account.tenantId -eq $CorporateTenantId) {
    throw "Refusing to deploy this personal project into the Microsoft corporate tenant."
}

$SupportedRegion = az functionapp list-flexconsumption-locations `
    --query "[?name=='$Location'].name | [0]" `
    --output tsv
if ($LASTEXITCODE -ne 0 -or -not $SupportedRegion) {
    throw "Azure Functions Flex Consumption is not available in '$Location' for this subscription."
}

foreach ($Namespace in @("Microsoft.Web", "Microsoft.Storage", "Microsoft.Insights")) {
    az provider register --namespace $Namespace --wait
    if ($LASTEXITCODE -ne 0) {
        throw "Could not register Azure resource provider '$Namespace'."
    }
}

$HashInput = "$SubscriptionId|$FunctionAppName"
$HashBytes = [System.Text.Encoding]::UTF8.GetBytes($HashInput)
$Hash = [System.Security.Cryptography.SHA256]::HashData($HashBytes)
$Suffix = ([Convert]::ToHexString($Hash)).Substring(0, 8).ToLowerInvariant()
$StorageAccount = "stastro$Suffix"

$ExistingGroup = az group exists --name $ResourceGroup
if ($ExistingGroup -ne "true") {
    az group create --name $ResourceGroup --location $Location --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create resource group '$ResourceGroup'."
    }
}

$ExistingStorage = az storage account show `
    --name $StorageAccount `
    --resource-group $ResourceGroup `
    --query name `
    --output tsv 2>$null
if (-not $ExistingStorage) {
    az storage account create `
        --name $StorageAccount `
        --location $Location `
        --resource-group $ResourceGroup `
        --sku Standard_LRS `
        --allow-blob-public-access false `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create storage account '$StorageAccount'."
    }
}

$ExistingFunctionApp = az functionapp show `
    --name $FunctionAppName `
    --resource-group $ResourceGroup `
    --query name `
    --output tsv 2>$null
if (-not $ExistingFunctionApp) {
    az functionapp create `
        --resource-group $ResourceGroup `
        --name $FunctionAppName `
        --storage-account $StorageAccount `
        --flexconsumption-location $Location `
        --runtime python `
        --runtime-version 3.11 `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create function app '$FunctionAppName'. The name may already be in use."
    }
}

az functionapp scale config set `
    --name $FunctionAppName `
    --resource-group $ResourceGroup `
    --maximum-instance-count 2 `
    --output none
if ($LASTEXITCODE -ne 0) {
    throw "Could not apply the function app scale limit."
}

$Cors = az functionapp cors show `
    --name $FunctionAppName `
    --resource-group $ResourceGroup `
    --output json | ConvertFrom-Json
if ($PagesOrigin -notin $Cors.allowedOrigins) {
    az functionapp cors add `
        --name $FunctionAppName `
        --resource-group $ResourceGroup `
        --allowed-origins $PagesOrigin `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Could not allow the GitHub Pages origin in the function app CORS policy."
    }
}

$StageDirectory = Join-Path $env:TEMP ("ireland-astro-api-" + [Guid]::NewGuid().ToString("N"))
$PackagePath = "$StageDirectory.zip"
try {
    New-Item -ItemType Directory -Path "$StageDirectory\src" -Force | Out-Null
    Copy-Item "$RepositoryRoot\function_app.py" $StageDirectory
    Copy-Item "$RepositoryRoot\host.json" $StageDirectory
    Copy-Item "$RepositoryRoot\requirements.txt" $StageDirectory
    Copy-Item `
        "$RepositoryRoot\src\meteoblue_seeing" `
        "$StageDirectory\src\meteoblue_seeing" `
        -Recurse

    Get-ChildItem $StageDirectory -Directory -Recurse -Filter "__pycache__" |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Get-ChildItem $StageDirectory -File -Recurse -Filter "*.pyc" |
        Remove-Item -Force

    Compress-Archive -Path "$StageDirectory\*" -DestinationPath $PackagePath -Force

    az functionapp deployment source config-zip `
        --resource-group $ResourceGroup `
        --name $FunctionAppName `
        --src $PackagePath `
        --build-remote true `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure Functions package deployment failed."
    }
}
finally {
    if (Test-Path -LiteralPath $StageDirectory) {
        Remove-Item -LiteralPath $StageDirectory -Recurse -Force
    }
    if (Test-Path -LiteralPath $PackagePath) {
        Remove-Item -LiteralPath $PackagePath -Force
    }
}

$ApiBase = "https://$FunctionAppName.azurewebsites.net"
$HealthUrl = "$ApiBase/api/health"
$Healthy = $false
for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
    try {
        $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 20
        if ($Health.status -eq "ok") {
            $Healthy = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 10
    }
}
if (-not $Healthy) {
    throw "Deployment completed, but the health endpoint did not become ready: $HealthUrl"
}

Write-Output "API deployed and healthy: $ApiBase"
Write-Output "Connect GitHub Pages with:"
Write-Output "python scripts\build_pages.py --api-base `"$ApiBase`""
