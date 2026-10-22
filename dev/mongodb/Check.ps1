. (Join-Path $PSScriptRoot 'Common.ps1')
$running = Get-RecordedProcess
Assert-ProjectListener $running
Invoke-ProjectShell 'check'
Write-Output "Verified project PID=$($running.Id); URI=$AppUri"
