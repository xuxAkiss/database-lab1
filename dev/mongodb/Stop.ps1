. (Join-Path $PSScriptRoot 'Common.ps1')
$null = Read-Owner
if (-not (Test-Path -LiteralPath $ProcessPath)) {
    if (@(Get-PortOwner).Count -gt 0) { throw 'Port is occupied but there is no project process record.' }
    Write-Output 'Project instance is already stopped.'
    exit 0
}
$record = Get-Content -LiteralPath $ProcessPath -Raw | ConvertFrom-Json
if (-not (Get-Process -Id $record.pid -ErrorAction SilentlyContinue)) {
    if (@(Get-PortOwner).Count -gt 0) { throw 'Port is occupied by another process; it was not touched.' }
    Write-Output 'Recorded project process is already stopped.'
    exit 0
}
$running = Assert-OwnedProcess ([int]$record.pid) $record.startTimeUtcTicks
Assert-ProjectListener $running
Invoke-ProjectShell 'shutdown'
if (-not $running.WaitForExit(30000)) {
    throw 'Graceful shutdown did not finish in 30 seconds. No forced kill was attempted.'
}
if (@(Get-PortOwner).Count -gt 0) { throw 'Shutdown completed but the port is now occupied. Inspect ownership.' }
Write-Output "Stopped project PID=$($record.pid). Data directory preserved: $DataPath"
