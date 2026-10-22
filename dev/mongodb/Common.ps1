$ErrorActionPreference = 'Stop'
$Workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Runtime = Join-Path $Workspace '.local\mongodb'
$DataPath = Join-Path $Runtime 'data'
$LogPath = Join-Path $Runtime 'logs'
$ConfigPath = Join-Path $PSScriptRoot 'mongod.cfg'
$ConfigArgument = 'dev\mongodb\mongod.cfg'
$OwnerPath = Join-Path $Runtime 'owner.json'
$ProcessPath = Join-Path $Runtime 'process.json'
$Mongod = 'D:\Mongodb\bin\mongod.exe'
$Mongosh = 'D:\Mongodb\bin\mongosh.exe'
$Port = 27018
$ReplicaSet = 'work1DevRs'
$DirectUri = 'mongodb://127.0.0.1:27018/?directConnection=true&serverSelectionTimeoutMS=3000&connectTimeoutMS=3000'
$AppUri = 'mongodb://127.0.0.1:27018/work1?replicaSet=work1DevRs&serverSelectionTimeoutMS=5000'

function Write-JsonFile($Value, [string]$Path) {
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-PortOwner {
    # Enumerate listeners first: an empty result is different from a failed query.
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -eq $Port })
    return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Assert-OwnedProcess([int]$ProcessId, $ExpectedTicks = $null) {
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $p) { throw "Recorded process $ProcessId is not running." }
    $c = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    if (-not $c -or $c.ExecutablePath -ine $Mongod) {
        throw "Process $ProcessId is not the expected mongod executable."
    }
    $configArgument = '(?i)(?:^|\s)--config\s+"?' + [regex]::Escape($ConfigArgument) + '"?(?:\s|$)'
    if (-not $c.CommandLine -or $c.CommandLine -notmatch $configArgument) {
        throw "Process $ProcessId does not use this project's exact config."
    }
    if ($null -ne $ExpectedTicks -and [string]$p.StartTime.ToUniversalTime().Ticks -ne [string]$ExpectedTicks) {
        throw "PID reuse detected; refusing to operate on process $ProcessId."
    }
    return $p
}

function Read-Owner {
    if (-not (Test-Path -LiteralPath $OwnerPath)) { throw 'Project ownership marker is missing.' }
    $owner = Get-Content -LiteralPath $OwnerPath -Raw | ConvertFrom-Json
    if ($owner.workspace -ine $Workspace -or $owner.dataPath -ine $DataPath -or
        $owner.configPath -ine $ConfigPath -or $owner.port -ne $Port -or
        $owner.replicaSet -ne $ReplicaSet) {
        throw 'Ownership marker does not match this project. Nothing was reset.'
    }
    return $owner
}

function Save-ProcessRecord($Process) {
    Write-JsonFile ([ordered]@{
        pid = $Process.Id
        startTimeUtcTicks = [string]$Process.StartTime.ToUniversalTime().Ticks
        executable = $Mongod
        configPath = $ConfigPath
        dataPath = $DataPath
        port = $Port
        replicaSet = $ReplicaSet
    }) $ProcessPath
}

function Get-RecordedProcess {
    $null = Read-Owner
    if (-not (Test-Path -LiteralPath $ProcessPath)) { throw 'No project process record. Run Start.ps1 first.' }
    $record = Get-Content -LiteralPath $ProcessPath -Raw | ConvertFrom-Json
    return Assert-OwnedProcess ([int]$record.pid) $record.startTimeUtcTicks
}

function Assert-ProjectListener($Process) {
    $owners = @(Get-PortOwner)
    if ($owners.Count -ne 1 -or $owners[0] -ne $Process.Id) {
        throw "Port $Port is not exclusively owned by the verified project process."
    }
}

function Invoke-ProjectShell([string]$Mode, [bool]$AllowInit = $false) {
    # Confine mongosh's own profile/logs to this workspace as well.
    $variables = @{
        APPDATA = (Join-Path $Runtime 'client-profile')
        WORK1_MONGO_MODE = $Mode
        WORK1_MONGO_DATA = $DataPath
        WORK1_MONGO_INIT_ALLOWED = ([string]$AllowInit).ToLowerInvariant()
    }
    $previous = @{}
    foreach ($key in $variables.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $variables[$key], 'Process')
    }
    try {
        $uri = if ($Mode -eq 'check') { $AppUri } else { $DirectUri }
        & $Mongosh $uri --quiet --norc --file (Join-Path $PSScriptRoot 'admin.js')
        if ($LASTEXITCODE -ne 0) { throw "mongosh failed with exit code $LASTEXITCODE." }
    } finally {
        foreach ($key in $variables.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
        }
    }
}
