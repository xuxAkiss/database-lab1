. (Join-Path $PSScriptRoot 'Common.ps1')
foreach ($file in @($Mongod, $Mongosh, $ConfigPath)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file" }
}

$owners = @(Get-PortOwner)
if ($owners.Count -gt 0) {
    if ($owners.Count -ne 1) { throw "Port $Port has multiple owners; nothing will be stopped." }
    $null = Read-Owner
    $existing = Get-RecordedProcess
    Assert-ProjectListener $existing
    Invoke-ProjectShell 'check'
    Write-Output "Already running: PID=$($existing.Id); URI=$AppUri"
    exit 0
}

if (Test-Path -LiteralPath $ProcessPath) {
    $record = Get-Content -LiteralPath $ProcessPath -Raw | ConvertFrom-Json
    if (Get-Process -Id $record.pid -ErrorAction SilentlyContinue) {
        throw 'Recorded PID is still alive but not listening. Inspect it; no second process was started.'
    }
}

if (-not (Test-Path -LiteralPath $OwnerPath)) {
    if ((Test-Path -LiteralPath $Runtime) -and
        @(Get-ChildItem -LiteralPath $Runtime -Force).Count -gt 0) {
        throw 'Runtime directory has existing contents without an ownership marker. Refusing initialization.'
    }
    New-Item -ItemType Directory -Path $DataPath, $LogPath, (Join-Path $Runtime 'client-profile') -Force | Out-Null
    Write-JsonFile ([ordered]@{
        workspace = $Workspace
        dataPath = $DataPath
        configPath = $ConfigPath
        port = $Port
        replicaSet = $ReplicaSet
        initializationPending = $true
        createdAtUtc = [DateTime]::UtcNow.ToString('o')
    }) $OwnerPath
}
$owner = Read-Owner
if (-not (Test-Path -LiteralPath $DataPath -PathType Container)) {
    throw 'Owned data directory is missing. Refusing to silently recreate it.'
}
if (-not $owner.initializationPending -and @(Get-ChildItem -LiteralPath $DataPath -Force).Count -eq 0) {
    throw 'Previously initialized data directory is empty. Refusing reinitialization.'
}

$started = Start-Process -FilePath $Mongod -ArgumentList @('--config', $ConfigArgument) -WorkingDirectory $Workspace `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $LogPath 'startup.stdout.log') `
    -RedirectStandardError (Join-Path $LogPath 'startup.stderr.log')
Save-ProcessRecord $started
$deadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    $started.Refresh()
    if ($started.HasExited) {
        throw "mongod exited with code $($started.ExitCode). Inspect $LogPath. No data was removed."
    }
    $listeners = @(Get-PortOwner)
    if ($listeners.Count -gt 0) {
        $null = Assert-OwnedProcess $started.Id
        Assert-ProjectListener $started
        break
    }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
Assert-ProjectListener $started
Invoke-ProjectShell 'initialize' ([bool]$owner.initializationPending)
$owner.initializationPending = $false
Write-JsonFile $owner $OwnerPath
Write-Output "Started: PID=$($started.Id); URI=$AppUri"
