[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('Capture', 'Start', 'ReturnToSource')][string]$Mode)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'user-encrypted-backup.ps1')
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$evidence = Join-Path $root 'backups/20260907-joint-local-encrypted'
$compose = @('compose', '--project-directory', $root, '-f', (Join-Path $root 'infra/docker/joint-restore.compose.yml'), '-f', (Join-Path $root 'infra/docker/joint-restore-runtime.compose.yml'))
function Docker-Text([string[]]$Arguments) {
    return [Text.Encoding]::UTF8.GetString((Invoke-BackupProcess 'docker' $Arguments)).Trim()
}
function Require-Project([string]$Container, [string]$Project) {
    if ((Docker-Text @('inspect', $Container, '--format', '{{ index .Config.Labels "com.docker.compose.project" }}')) -ne $Project) { throw 'Unexpected rehearsal container' }
}
Require-Project 'trade-fresh-acceptance-web-1' 'trade-fresh-acceptance'
Require-Project 'trade-workbench-logto-1' 'trade-workbench'
Require-Project 'trade-joint-restore-v2-postgres-1' 'trade-joint-restore-v2'
Require-Project 'trade-joint-restore-v2-logto-postgres-1' 'trade-joint-restore-v2'
$runtimePath = Join-Path $evidence 'runtime-config.dpapi'
if ($Mode -eq 'Capture') {
    $sourceEnvironment = (Docker-Text @('inspect', 'trade-workbench-logto-1', '--format', '{{json .Config.Env}}')) | ConvertFrom-Json
    $url = @($sourceEnvironment | Where-Object { $_.StartsWith('DB_URL=') })
    if ($url.Count -ne 1 -or ([uri]$url[0].Substring(7)).Host -ne 'logto-postgres') { throw 'Unexpected identity database configuration' }
    $configuration = @{
        JOINT_LOGTO_DB_URL = $url[0].Substring(7)
        JOINT_API_IMAGE = Docker-Text @('inspect', 'trade-fresh-acceptance-api-1', '--format', '{{.Image}}')
        JOINT_WEB_IMAGE = Docker-Text @('inspect', 'trade-fresh-acceptance-web-1', '--format', '{{.Image}}')
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($configuration | ConvertTo-Json -Compress))
    try { Save-EncryptedBackup $bytes $runtimePath 'runtime-config' }
    finally { [Array]::Clear($bytes, 0, $bytes.Length); $configuration=$null; $sourceEnvironment=$null; $url=$null }
    Write-Output 'Runtime credentials and immutable image identities saved encrypted; no service changes.'
    return
}
if ($Mode -eq 'ReturnToSource') {
    foreach ($name in @('web','api','logto','redis')) {
        $container = "trade-joint-restore-v2-$name-1"
        Require-Project $container 'trade-joint-restore-v2'
        $null = Docker-Text @('stop', '--time', '20', $container)
    }
    $null = Docker-Text @('start', 'trade-workbench-logto-1', 'trade-fresh-acceptance-web-1')
    Write-Output 'Original identity and Web restarted; restored data retained.'
    return
}
$bytes = Unprotect-BackupBytes ([IO.File]::ReadAllBytes($runtimePath)) 'runtime-config'
$saved = @{}
$stopped = [Collections.Generic.List[string]]::new()
try {
    $configuration = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json -AsHashtable
    $webBytes = Unprotect-BackupBytes ([IO.File]::ReadAllBytes((Join-Path $evidence 'web-secrets.dpapi'))) 'web-secrets'
    try {
        $web = [Text.Encoding]::UTF8.GetString($webBytes) | ConvertFrom-Json
        $configuration.JOINT_APP_SECRET = ($web | Where-Object { $_.StartsWith('LOGTO_APP_SECRET=') }).Substring(17)
        $configuration.JOINT_COOKIE_SECRET = ($web | Where-Object { $_.StartsWith('LOGTO_COOKIE_SECRET=') }).Substring(20)
    } finally { [Array]::Clear($webBytes, 0, $webBytes.Length); $web=$null }
    foreach ($name in $configuration.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $configuration[$name], 'Process')
    }
    $null = Docker-Text ($compose + @('config', '--quiet'))
    foreach ($container in @('trade-fresh-acceptance-web-1', 'trade-workbench-logto-1')) {
        if ((Docker-Text @('inspect', $container, '--format', '{{.State.Running}}')) -ne 'true') { throw 'Original endpoint already stopped; inspect before switching' }
        $stopped.Add($container)
        $null = Docker-Text @('stop', '--time', '20', $container)
    }
    try {
        $null = Docker-Text ($compose + @('up', '-d', '--no-build', 'redis','logto','api','web'))
    } catch {
        $null = Docker-Text ($compose + @('stop', 'web','api','logto','redis'))
        throw
    }
    $stopped.Clear()
    Write-Output 'Restored endpoints now own localhost3300/3001/3002. Original Web/Logto are stopped with source volumes retained. Login verification required.'
} finally {
    foreach ($container in $stopped) { $null = Docker-Text @('start', $container) }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    [Array]::Clear($bytes, 0, $bytes.Length)
    $configuration=$null
}
