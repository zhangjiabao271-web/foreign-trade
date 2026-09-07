# Run only after the fresh + commercial-recovery overlays start postgres/minio.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$recoveryVariables = @{
    E2E_COMMERCIAL_RECOVERY = '1'
    TEST_DATABASE_ADMIN_URL = 'postgresql+psycopg://rehearsal:local-isolated-rehearsal-only@127.0.0.1:25432/postgres'
    MINIO_HOST = '127.0.0.1'
    MINIO_PORT = '29000'
    MINIO_PUBLIC_ENDPOINT = '127.0.0.1:29000'
    MINIO_SECURE = 'false'
    MINIO_PUBLIC_SECURE = 'false'
    MINIO_ACCESS_KEY = 'rehearsal'
    MINIO_SECRET_KEY = 'local-isolated-rehearsal-only'
    MINIO_BUCKET = 'trade-commercial-recovery'
}
$previousVariables = @{}
foreach ($key in $recoveryVariables.Keys) {
    $previousVariables[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $recoveryVariables[$key], 'Process')
}
Push-Location (Join-Path $workspacePath 'apps/web')
try {
    & './node_modules/.bin/playwright.CMD' test
    if ($LASTEXITCODE -ne 0) { throw 'Recovery browser fixture failed; retained evidence must be inspected, never overwritten.' }
} finally {
    Pop-Location
    foreach ($key in $previousVariables.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousVariables[$key], 'Process')
    }
}
