# Cold object-volume restore plus PostgreSQL logical restore, synthetic isolated stack only.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$backupPath = [IO.Path]::GetFullPath((Join-Path $workspacePath 'backups/20260907-commercial-recovery'))
$expectedBackupParent = [IO.Path]::GetFullPath((Join-Path $workspacePath 'backups'))
if ([IO.Directory]::GetParent($backupPath).FullName -ne $expectedBackupParent) {
    throw 'Backup path escaped its intended workspace directory.'
}
$project = 'trade-fresh-acceptance'
$sourceDatabase = 'trade-fresh-acceptance-postgres-1'
$sourceStorage = 'trade-fresh-acceptance-minio-1'
$targetDatabase = 'trade-fresh-acceptance-commercial-postgres-restored-1'
$targetStorage = 'trade-fresh-acceptance-commercial-minio-restored-1'
$sourceVolume = 'trade-fresh-acceptance_minio-data'
$targetVolume = 'trade-fresh-acceptance_commercial-minio-restored-data'
$databaseVolume = 'trade-fresh-acceptance_commercial-postgres-restored-data'
$composeArgs = @('compose', '-p', $project, '--project-directory', $workspacePath,
    '-f', (Join-Path $workspacePath 'docker-compose.yml'),
    '-f', (Join-Path $workspacePath 'infra/docker/fresh.compose.yml'),
    '-f', (Join-Path $workspacePath 'infra/docker/commercial-recovery.compose.yml'))

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed (exit $LASTEXITCODE)." }
    return $output
}

if (-not (Test-Path -LiteralPath (Join-Path $backupPath 'source-manifest.json'))) {
    throw 'Capture and validate the complete source manifest first.'
}
foreach ($file in @('business.dump', 'minio.tgz', 'verification.json')) {
    if (Test-Path -LiteralPath (Join-Path $backupPath $file)) { throw 'Recovery evidence exists; refusing overwrite.' }
}
foreach ($name in @($targetVolume, $databaseVolume)) {
    $existing = Invoke-Docker @('volume', 'ls', '--filter', "name=^${name}$", '--format', '{{.Name}}')
    if ($existing) { throw 'Restore volumes already exist; refusing reuse.' }
}
foreach ($container in @($sourceDatabase, $sourceStorage)) {
    $label = Invoke-Docker @('inspect', $container, '--format', '{{ index .Config.Labels "com.docker.compose.project" }}')
    if ($label.Trim() -ne $project) { throw 'Unexpected source project.' }
}
$mounts = (Invoke-Docker @('inspect', $sourceStorage, '--format', '{{json .Mounts}}')) | ConvertFrom-Json
if (($mounts | Where-Object Destination -eq '/data').Name -ne $sourceVolume) { throw 'Unexpected source storage volume.' }
foreach ($service in @('api', 'web', 'worker', 'worker-beat')) {
    $running = Invoke-Docker @('inspect', "${project}-${service}-1", '--format', '{{.State.Running}}')
    if ($running.Trim() -ne 'false') { throw 'Application writers must already be stopped.' }
}
$sessions = Invoke-Docker @('exec', $sourceDatabase, 'psql', '-U', 'rehearsal', '-d', 'trade_workbench_e2e', '-Atc', "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'")
if ($sessions.Trim() -ne '0') { throw 'Browser/database clients are still connected.' }

# Preserve the source volume and original immutable object version IDs. Never archive a live volume.
Invoke-Docker ($composeArgs + @('stop', 'minio'))
try {
    Invoke-Docker @('exec', $sourceDatabase, 'pg_dump', '-U', 'rehearsal', '-d', 'trade_workbench_e2e', '-Fc', '-f', '/tmp/commercial-recovery.dump')
    Invoke-Docker @('cp', "${sourceDatabase}:/tmp/commercial-recovery.dump", (Join-Path $backupPath 'business.dump'))
    Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', "type=volume,source=$sourceVolume,target=/source,readonly", '--mount', "type=bind,source=$backupPath,target=/backup", '--entrypoint', 'tar', 'postgres:18-bookworm', '-czf', '/backup/minio.tgz', '-C', '/source', '.')
} finally {
    Invoke-Docker ($composeArgs + @('start', 'minio'))
}

# Brand-new target volumes only. No --clean, overwrite, volume deletion or data remapping.
Invoke-Docker ($composeArgs + @('up', '-d', '--wait', '--wait-timeout', '45', 'commercial-postgres-restored'))
$tables = Invoke-Docker @('exec', $targetDatabase, 'psql', '-U', 'rehearsal', '-d', 'trade_workbench_e2e', '-Atc', "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
if ($tables.Trim() -ne '0') { throw 'Restore database is not empty.' }
Invoke-Docker ($composeArgs + @('create', 'commercial-minio-restored'))
$running = Invoke-Docker @('inspect', $targetStorage, '--format', '{{.State.Running}}')
if ($running.Trim() -ne 'false') { throw 'Restore object store must be stopped.' }
$files = Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', "type=volume,source=$targetVolume,target=/target,readonly", '--entrypoint', 'find', 'postgres:18-bookworm', '/target', '-mindepth', '1', '-print', '-quit')
if ($files) { throw 'Restore object volume is not empty.' }
Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', "type=volume,source=$targetVolume,target=/target", '--mount', "type=bind,source=$backupPath,target=/backup,readonly", '--entrypoint', 'tar', 'postgres:18-bookworm', '-xzf', '/backup/minio.tgz', '-C', '/target')
Invoke-Docker @('cp', (Join-Path $backupPath 'business.dump'), "${targetDatabase}:/tmp/commercial-recovery.dump")
Invoke-Docker @('exec', $targetDatabase, 'pg_restore', '-U', 'rehearsal', '-d', 'trade_workbench_e2e', '--exit-on-error', '--no-owner', '--no-acl', '/tmp/commercial-recovery.dump')
Invoke-Docker ($composeArgs + @('up', '-d', '--wait', '--wait-timeout', '45', 'commercial-minio-restored'))
& (Join-Path $workspacePath '.venv/Scripts/python.exe') (Join-Path $workspacePath 'apps/api/scripts/commercial_recovery_probe.py') verify
if ($LASTEXITCODE -ne 0) { throw 'Commercial restore verification failed; preserve all evidence for diagnosis.' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupPath 'business.dump'), (Join-Path $backupPath 'minio.tgz'), (Join-Path $backupPath 'source-manifest.json') | Select-Object Hash, Path
