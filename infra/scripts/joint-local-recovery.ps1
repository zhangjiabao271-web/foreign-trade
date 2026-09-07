# Only for the user-authorized local DPAPI acceptance rehearsal. Never a production backup job.
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('Check', 'Backup', 'Restore', 'VerifyRoles', 'VerifySchema')][string]$Mode)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'user-encrypted-backup.ps1')
. (Join-Path $PSScriptRoot 'backup-schema-normalization.ps1')
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$evidence = Join-Path $root 'backups/20260907-joint-local-encrypted'
$compose = @('compose', '--project-directory', $root, '-f', (Join-Path $root 'infra/docker/joint-restore.compose.yml'))
$databases = @(
    @{ Name='trade_fresh_acceptance'; Source='trade-fresh-acceptance-postgres-1'; User='rehearsal'; Target='trade-joint-restore-v2-postgres-1' },
    @{ Name='trade_workbench_e2e'; Source='trade-fresh-acceptance-postgres-1'; User='rehearsal'; Target='trade-joint-restore-v2-postgres-1' },
    @{ Name='logto'; Source='trade-workbench-logto-postgres-1'; User='logto'; Target='trade-joint-restore-v2-logto-postgres-1' }
)
$fingerprintSql = @'
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL TIME ZONE 'UTC';
SELECT format('SELECT %L,count(*),encode(sha256(convert_to(coalesce(string_agg(to_jsonb(t)::text,E''\n'' ORDER BY to_jsonb(t)::text),''''),''UTF8'')),''hex'') FROM %I.%I t;', schemaname||'.'||tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename
\gexec
COMMIT;
'@
function Docker-Bytes([string[]]$Arguments, [byte[]]$InputBytes) {
    return ,(Invoke-BackupProcess 'docker' $Arguments -InputBytes $InputBytes)
}
function Docker-Text([string[]]$Arguments) {
    return [Text.Encoding]::UTF8.GetString((Docker-Bytes $Arguments)).Trim()
}
function Require-Project([string]$Container, [string]$Project) {
    $label = Docker-Text @('inspect', $Container, '--format', '{{ index .Config.Labels "com.docker.compose.project" }}')
    if ($label -ne $Project) { throw 'Unexpected source or target project' }
}
function Save-Package([string]$Name, [byte[]]$Bytes) {
    try { Save-EncryptedBackup $Bytes (Join-Path $evidence "$Name.dpapi") $Name }
    finally { [Array]::Clear($Bytes, 0, $Bytes.Length) }
}
function Read-Package([string]$Name) {
    return ,(Unprotect-BackupBytes ([IO.File]::ReadAllBytes((Join-Path $evidence "$Name.dpapi"))) $Name)
}
function Fingerprint([string]$Container, [string]$Database, [string]$User) {
    return ,(Docker-Bytes @('exec', '-i', $Container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', $User, '-d', $Database, '-f', '-') ([Text.Encoding]::UTF8.GetBytes($fingerprintSql)))
}

foreach ($database in $databases) {
    $project = if ($database.User -eq 'logto') { 'trade-workbench' } else { 'trade-fresh-acceptance' }
    Require-Project $database.Source $project
}
Require-Project 'trade-fresh-acceptance-minio-1' 'trade-fresh-acceptance'
$mounts = (Docker-Text @('inspect', 'trade-fresh-acceptance-minio-1', '--format', '{{json .Mounts}}')) | ConvertFrom-Json
if (($mounts | Where-Object Destination -eq '/data').Name -ne 'trade-fresh-acceptance_minio-data') { throw 'Unexpected source object volume' }
$null = Docker-Text ($compose + @('config', '--quiet'))
if ($Mode -eq 'Check') { Write-Output 'PASS: fixed sources, object volume and port-free independent restore configuration'; return }

if ($Mode -eq 'Backup') {
    if (Test-Path -LiteralPath $evidence) { throw 'Backup directory exists; refusing reuse or overwrite' }
    $null = New-Item -ItemType Directory -Path $evidence
    $writers = @('trade-fresh-acceptance-web-1', 'trade-fresh-acceptance-api-1', 'trade-fresh-acceptance-worker-1', 'trade-fresh-acceptance-worker-beat-1', 'trade-workbench-logto-1')
    $restart = [Collections.Generic.List[string]]::new()
    try {
        foreach ($container in $writers + @('trade-fresh-acceptance-minio-1')) {
            $expected = if ($container -eq 'trade-workbench-logto-1') { 'trade-workbench' } else { 'trade-fresh-acceptance' }
            Require-Project $container $expected
            if ((Docker-Text @('inspect', $container, '--format', '{{.State.Running}}')) -eq 'true') {
                $restart.Add($container)
                $null = Docker-Text @('stop', '--time', '20', $container)
            }
        }
        foreach ($database in $databases) {
            $sessions = Docker-Text @('exec', $database.Source, 'psql', '-XAt', '-U', $database.User, '-d', $database.Name, '-c', "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'")
            if ($sessions -ne '0') { throw 'Source database still has clients; refusing inconsistent capture' }
            Save-Package "$($database.Name)-rows" (Fingerprint $database.Source $database.Name $database.User)
            Save-Package "$($database.Name)-database" (Docker-Bytes @('exec', $database.Source, 'pg_dump', '-U', $database.User, '-d', $database.Name, '-Fc'))
            Write-Output "Encrypted database captured: $($database.Name)"
        }
        foreach ($database in @($databases[0], $databases[2])) {
            Save-Package "$($database.User)-roles" (Docker-Bytes @('exec', $database.Source, 'pg_dumpall', '-U', $database.User, '--roles-only'))
        }
        Save-Package 'objects' (Docker-Bytes @('run', '--rm', '--network', 'none', '--mount', 'type=volume,source=trade-fresh-acceptance_minio-data,target=/source,readonly', '--entrypoint', 'tar', 'postgres:18-bookworm', '-czf', '-', '-C', '/source', '.'))
        # Select only credentials needed by the existing acceptance Web; never output env dumps.
        $environment = (Docker-Text @('inspect', 'trade-fresh-acceptance-web-1', '--format', '{{json .Config.Env}}')) | ConvertFrom-Json
        $selected = @($environment | Where-Object { $_ -match '^(LOGTO_APP_SECRET|LOGTO_COOKIE_SECRET)=' })
        if ($selected.Count -ne 2) { throw 'Required acceptance credentials missing' }
        Save-Package 'web-secrets' ([Text.Encoding]::UTF8.GetBytes(($selected | ConvertTo-Json -Compress)))
        $environment = $null; $selected = $null
        Save-Package 'complete' ([Text.Encoding]::UTF8.GetBytes('local-current-user-backup-v1'))
        Write-Output 'Encrypted capture complete. All source services will return to their previous running state.'
    } finally {
        $failedRestarts = [Collections.Generic.List[string]]::new()
        foreach ($container in $restart) {
            try { $null = Docker-Text @('start', $container) } catch { $failedRestarts.Add($container) }
        }
        if ($failedRestarts.Count) { throw "Source restart requires attention: $($failedRestarts -join ', ')" }
    }
    return
}

$null = Read-Package 'complete'
if ($Mode -eq 'VerifySchema') {
    foreach ($database in $databases) {
        Require-Project $database.Target 'trade-joint-restore-v2'
        $archive = Read-Package "$($database.Name)-database"
        $expected = $null
        $actual = $null
        try {
            # No database argument: pg_restore emits SQL to memory and never executes it.
            $expected = Docker-Bytes @('exec', '-i', $database.Target, 'pg_restore', '--schema-only', '--file=-') $archive
            $actual = Docker-Bytes @('exec', $database.Target, 'pg_dump', '-U', $database.User, '-d', $database.Name, '--schema-only')
            $normalized = foreach ($value in @($expected, $actual)) {
                ConvertTo-ComparableBackupSchema ([Text.Encoding]::UTF8.GetString($value))
            }
            if ($normalized[0] -cne $normalized[1]) { throw "Restored schema SQL differs: $($database.Name); contents withheld" }
            Write-Output "PASS: schema SQL, functions, owners and object grants match encrypted archive (enum cast normalization): $($database.Name)"
        } finally {
            foreach ($bytes in @($archive, $expected, $actual)) {
                if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
            }
            $normalized=$null
        }
    }
    return
}
if ($Mode -eq 'VerifyRoles') {
    foreach ($database in @($databases[0], $databases[2])) {
        Require-Project $database.Target 'trade-joint-restore-v2'
        $expected = Read-Package "$($database.User)-roles"
        $actual = Docker-Bytes @('exec', $database.Target, 'pg_dumpall', '-U', $database.User, '--roles-only')
        try {
            # pg_dump headers and random psql restrict markers are not role/ACL definitions.
            $normalized = foreach ($value in @($expected, $actual)) {
                $lines = [Text.Encoding]::UTF8.GetString($value) -split "`n"
                (($lines | Where-Object { $_.Trim() -and $_ -notmatch '^(--|\\restrict |\\unrestrict )' }) -join "`n").Trim()
            }
            if ($normalized[0] -cne $normalized[1]) { throw 'Restored role declarations, credentials or grants differ' }
            Write-Output "PASS: exact role declarations, password records and original grants: $($database.User)"
        } finally { [Array]::Clear($expected,0,$expected.Length); [Array]::Clear($actual,0,$actual.Length); $normalized=$null; $lines=$null }
    }
    return
}
foreach ($volume in @('business-data', 'identity-data', 'object-data')) {
    if (Docker-Text @('volume', 'ls', '--filter', "name=^trade-joint-restore-v2_${volume}$", '--format', '{{.Name}}')) { throw 'Restore volume exists; refusing reuse' }
}
$null = Docker-Text ($compose + @('up', '-d', '--wait', '--wait-timeout', '45', 'postgres', 'logto-postgres'))
foreach ($database in @($databases[0], $databases[2])) {
    Require-Project $database.Target 'trade-joint-restore-v2'
    $bytes = Read-Package "$($database.User)-roles"
    try {
        $sql = [Text.Encoding]::UTF8.GetString($bytes)
        $grantLines = @($sql -split "`n" | Where-Object { $_ -match '^GRANT ' })
        foreach ($line in $grantLines) {
            if ($line -notmatch (' GRANTED BY ' + [regex]::Escape($database.User) + ';\s*$')) { throw 'Unexpected original role grantor' }
        }
        # The original bootstrap user must remain OID 10, preserving original grantor semantics.
        $bootstrap = Docker-Text @('exec', $database.Target, 'psql', '-XAt', '-U', $database.User, '-d', 'postgres', '-c', "SELECT oid FROM pg_roles WHERE rolname=current_user AND rolsuper")
        if ($bootstrap -ne '10') { throw 'Restore bootstrap role identity differs from source' }
        $create = '(?m)^CREATE ROLE ' + [regex]::Escape($database.User) + ';\r?$'
        if ([regex]::Matches($sql, $create).Count -ne 1) { throw 'Unexpected role dump bootstrap declaration' }
        $sql = [regex]::Replace($sql, $create, '')
        $restoreSql = [Text.Encoding]::UTF8.GetBytes($sql)
        try { $null = Docker-Bytes @('exec', '-i', $database.Target, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', $database.User, '-d', 'postgres') $restoreSql }
        finally { [Array]::Clear($restoreSql, 0, $restoreSql.Length); $sql = $null; $grantLines = $null }
    }
    finally { [Array]::Clear($bytes, 0, $bytes.Length) }
}
foreach ($database in $databases) {
    $null = Docker-Text @('exec', $database.Target, 'createdb', '-U', $database.User, '-O', $database.User, $database.Name)
    $bytes = Read-Package "$($database.Name)-database"
    try { $null = Docker-Bytes @('exec', '-i', $database.Target, 'pg_restore', '-U', $database.User, '-d', $database.Name, '--exit-on-error') $bytes }
    finally { [Array]::Clear($bytes, 0, $bytes.Length) }
    $expected = Read-Package "$($database.Name)-rows"
    $actual = Fingerprint $database.Target $database.Name $database.User
    try {
        if ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($expected)) -ne [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($actual))) { throw 'Restored table fingerprints differ' }
        Write-Output "PASS: every table row fingerprint restored: $($database.Name)"
    } finally { [Array]::Clear($expected, 0, $expected.Length); [Array]::Clear($actual, 0, $actual.Length) }
}
$null = Docker-Text ($compose + @('create', 'minio'))
$bytes = Read-Package 'objects'
try { $null = Docker-Bytes @('run', '--rm', '-i', '--network', 'none', '--mount', 'type=volume,source=trade-joint-restore-v2_object-data,target=/target', '--entrypoint', 'tar', 'postgres:18-bookworm', '-xzf', '-', '-C', '/target') $bytes }
finally { [Array]::Clear($bytes, 0, $bytes.Length) }
$null = Docker-Text ($compose + @('up', '-d', '--wait', '--wait-timeout', '45', 'minio'))
Save-Package 'restored-rows' ([Text.Encoding]::UTF8.GetBytes('three-databases-row-fingerprints-match-v1'))
Write-Output 'Database rows restored and object volume extracted. Application, identity login and immutable-object verification remain required.'
