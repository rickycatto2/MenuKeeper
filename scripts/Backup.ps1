param([string]$Destination = (Join-Path $PSScriptRoot '..\backups'))
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$archive = Join-Path (Resolve-Path $Destination).Path "menukeeper-$(Get-Date -Format 'yyyyMMdd-HHmmss').zip"
Push-Location $project
try {
    docker compose stop recipes
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the app; backup cancelled.' }
    try { Compress-Archive -LiteralPath (Join-Path $project 'data') -DestinationPath $archive }
    finally { docker compose start recipes }
    Write-Output "Cookbook backup: $archive"
    Write-Output 'The .env file is intentionally excluded. Keep a separate secure copy of credentials.'
} finally { Pop-Location }
