# Runs only against the explicitly named synthetic acceptance stack.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$backupPath = Join-Path $workspacePath 'backups/20260906-storage-restore'
$composeArgs = @('compose', '--project-directory', $workspacePath, '-f', (Join-Path $workspacePath 'infra/docker/recovery.compose.yml'))

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed (exit $LASTEXITCODE)." }
    return $output
}

foreach ($container in @('trade-recovery-acceptance-worker-1', 'trade-recovery-acceptance-postgres-1', 'trade-recovery-acceptance-postgres-restored-1', 'trade-recovery-acceptance-minio-source-1')) {
    $project = Invoke-Docker @('inspect', $container, '--format', '{{ index .Config.Labels "com.docker.compose.project" }}')
    if ($project.Trim() -ne 'trade-recovery-acceptance') { throw 'Unexpected project; refusing backup/restore.' }
}
if (Test-Path -LiteralPath $backupPath) { throw 'Backup evidence already exists; refusing overwrite.' }
$tables = Invoke-Docker @('exec', 'trade-recovery-acceptance-postgres-restored-1', 'psql', '-U', 'rehearsal', '-d', 'trade_recovery_acceptance', '-Atc', "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
if ($tables.Trim() -ne '0') { throw 'Restore database is not empty; refusing overwrite.' }
New-Item -ItemType Directory -Path $backupPath | Out-Null

# Stop every application writer in this isolated stack before taking the paired snapshot.
Invoke-Docker ($composeArgs + @('stop', '-t', '10', 'worker', 'minio-source'))
try {
    Invoke-Docker @('exec', 'trade-recovery-acceptance-postgres-1', 'pg_dump', '-U', 'rehearsal', '-d', 'trade_recovery_acceptance', '-Fc', '-f', '/tmp/storage-recovery.dump')
    Invoke-Docker @('cp', 'trade-recovery-acceptance-postgres-1:/tmp/storage-recovery.dump', (Join-Path $backupPath 'business.dump'))
    Invoke-Docker @('cp', 'trade-recovery-acceptance-worker-1:/tmp/storage-recovery-manifest.json', (Join-Path $backupPath 'manifest.json'))
    Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', 'type=volume,source=trade-recovery-acceptance_minio-source-data,target=/source,readonly', '--mount', "type=bind,source=$backupPath,target=/backup", '--entrypoint', 'tar', 'postgres:18-bookworm', '-czf', '/backup/minio.tgz', '-C', '/source', '.')
} finally {
    Invoke-Docker ($composeArgs + @('start', 'minio-source', 'worker'))
}

# Create but never start the object-store target until its empty volume has been restored.
Invoke-Docker ($composeArgs + @('create', 'minio-restored'))
$running = Invoke-Docker @('inspect', 'trade-recovery-acceptance-minio-restored-1', '--format', '{{.State.Running}}')
if ($running.Trim() -ne 'false') { throw 'Restore object store must be stopped.' }
$files = Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', 'type=volume,source=trade-recovery-acceptance_minio-restored-data,target=/target,readonly', '--entrypoint', 'find', 'postgres:18-bookworm', '/target', '-mindepth', '1', '-print', '-quit')
if ($files) { throw 'Restore volume is not empty; refusing overwrite.' }
Invoke-Docker @('run', '--rm', '--network', 'none', '--mount', 'type=volume,source=trade-recovery-acceptance_minio-restored-data,target=/target', '--mount', "type=bind,source=$backupPath,target=/backup,readonly", '--entrypoint', 'tar', 'postgres:18-bookworm', '-xzf', '/backup/minio.tgz', '-C', '/target')
Invoke-Docker @('cp', (Join-Path $backupPath 'business.dump'), 'trade-recovery-acceptance-postgres-restored-1:/tmp/storage-recovery.dump')
Invoke-Docker @('exec', 'trade-recovery-acceptance-postgres-restored-1', 'pg_restore', '-U', 'rehearsal', '-d', 'trade_recovery_acceptance', '--exit-on-error', '--no-owner', '--no-acl', '/tmp/storage-recovery.dump')
Invoke-Docker ($composeArgs + @('start', 'minio-restored'))
Invoke-Docker @('exec', '-e', 'DATABASE_HOST=postgres-restored', 'trade-recovery-acceptance-worker-1', 'python', '/tmp/storage_recovery_probe.py', 'verify')
Invoke-Docker @('exec', '-w', '/app/apps/api', '-e', 'DATABASE_HOST=postgres-restored', 'trade-recovery-acceptance-worker-1', 'alembic', '-c', 'alembic.ini', 'check')
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupPath 'business.dump'), (Join-Path $backupPath 'minio.tgz'), (Join-Path $backupPath 'manifest.json') | Select-Object Hash, Path
