param(
    [string]$ConfigPath = 'C:\cloudflared\config.yml',
    [string]$Hostname = 'recipes.pixelwood.co',
    [string]$ServiceName = 'CloudflaredOverseerr',
    [switch]$ConfigureDns,
    [switch]$RestartService
)
$ErrorActionPreference = 'Stop'
$original = [IO.File]::ReadAllText($ConfigPath)
& cloudflared tunnel --config $ConfigPath ingress validate
if ($LASTEXITCODE -ne 0) { throw 'Existing Cloudflare configuration is invalid; nothing changed.' }
$route = "  - hostname: $Hostname`r`n    service: http://localhost:5059`r`n`r`n"
if ($original -match "hostname:\s*$([regex]::Escape($Hostname))\s*\r?\n\s*service:\s*http://localhost:5059") {
    Write-Output 'The requested route already exists.'
} else {
    if ($original.Contains($Hostname)) { throw 'Hostname already exists with a different route; review manually.' }
    $catchall = [regex]::Matches($original, '(?m)^  - service: http_status:404\s*$')
    if ($catchall.Count -ne 1) { throw 'Expected one final 404 catch-all; nothing changed.' }
    $updated = $original.Insert($catchall[0].Index, $route)
    $candidate = "$ConfigPath.menukeeper-candidate.yml"
    [IO.File]::WriteAllText($candidate, $updated, [Text.UTF8Encoding]::new($false))
    & cloudflared tunnel --config $candidate ingress validate
    if ($LASTEXITCODE -ne 0) { throw 'Candidate validation failed; existing configuration was not changed.' }
    $backup = "$ConfigPath.pre-menukeeper-$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
    Copy-Item -LiteralPath $ConfigPath -Destination $backup
    [IO.File]::WriteAllText($ConfigPath, $updated, [Text.UTF8Encoding]::new($false))
    Write-Output "Added only the requested ingress rule. Backup: $backup"
}
& cloudflared tunnel --config $ConfigPath ingress validate
if ($LASTEXITCODE -ne 0) { throw 'Validation failed; service was not restarted.' }
& cloudflared tunnel --config $ConfigPath ingress rule "https://$Hostname"
if ($LASTEXITCODE -ne 0) { throw 'Rule check failed; service was not restarted.' }
if ($ConfigureDns) {
    $match = [regex]::Match($original, '(?m)^tunnel:\s*([^\r\n]+)')
    if (-not $match.Success) { throw 'Cannot find existing tunnel ID.' }
    & cloudflared tunnel route dns $match.Groups[1].Value.Trim() $Hostname
    if ($LASTEXITCODE -ne 0) { throw 'DNS route failed. Existing DNS records were not overwritten.' }
}
if ($RestartService) {
    Restart-Service -Name $ServiceName -ErrorAction Stop
    Get-Service -Name $ServiceName | Select-Object Name, Status
}
