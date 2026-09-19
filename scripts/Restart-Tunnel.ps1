$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot '..\data\tunnel-restart.log'
try {
    & 'C:\Program Files (x86)\cloudflared\cloudflared.exe' tunnel --config 'C:\cloudflared\config.yml' ingress validate 2>&1 | Out-File $log
    if ($LASTEXITCODE -ne 0) { throw 'Cloudflare configuration validation failed; restart cancelled.' }
    Restart-Service -Name CloudflaredOverseerr -ErrorAction Stop
    (Get-Service CloudflaredOverseerr | Select-Object Name,Status | Out-String) | Add-Content $log
} catch {
    $_.Exception.Message | Add-Content $log
    exit 1
}
