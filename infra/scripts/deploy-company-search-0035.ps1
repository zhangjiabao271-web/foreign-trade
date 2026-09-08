$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# One-time local acceptance deployment; keeps the five behavioral overlays intact.
$project = 'trade-fresh-acceptance'
$serviceNames = @('api', 'worker', 'worker-beat', 'web')
$containers = @{}
$previousEnv = @{}
$stopped = $false
$composeArgs = @('compose', '-p', $project, '-f', 'docker-compose.yml',
    '-f', 'infra/docker/fresh.compose.yml',
    '-f', 'infra/docker/identity-acceptance.compose.yml',
    '-f', 'infra/docker/acceptance-storage.compose.yml',
    '-f', 'infra/docker/deepseek-acceptance.compose.yml',
    '-f', 'infra/docker/release-0035.compose.yml')

function Read-Container([string]$name) {
    $result = @(docker inspect $name | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or $result.Count -ne 1) { throw 'Container inspection failed' }
    if ($result[0].Config.Labels.'com.docker.compose.project' -ne $project) {
        throw 'Container project rejected'
    }
    return $result[0]
}

function Set-TaskEnv([string]$key, [string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'Required credential unavailable' }
    $previousEnv[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}

function Container-Value($container, [string]$key) {
    $matches = @($container.Config.Env | Where-Object { $_.StartsWith("${key}=") })
    if ($matches.Count -ne 1) { throw 'Required container configuration absent' }
    return $matches[0].Substring($key.Length + 1)
}

try {
    if ((Resolve-Path '.').Path -ne 'D:\work\foreign_trade') { throw 'Workspace rejected' }
    $backup = 'D:\work\foreign_trade\backups\20260908-company-search-0035\business.dpapi'
    if ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash -ne
        'F59E137168EFB2C372C4E3151BE5CEEB799B2B99EA69BE605F38F6D6CA8E1339') {
        throw 'Verified encrypted backup differs'
    }
    foreach ($service in $serviceNames) {
        $containers[$service] = Read-Container "${project}-${service}-1"
        if (-not $containers[$service].State.Running) { throw 'Expected running service absent' }
    }
    $null = Read-Container "${project}-postgres-1"
    $network = @(docker network inspect "${project}_default" | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or $network[0].Labels.'com.docker.compose.project' -ne $project) {
        throw 'Network rejected'
    }
    Set-TaskEnv 'ACCEPTANCE_LOGTO_APP_SECRET' (Container-Value $containers['web'] 'LOGTO_APP_SECRET')
    Set-TaskEnv 'ACCEPTANCE_LOGTO_COOKIE_SECRET' (Container-Value $containers['web'] 'LOGTO_COOKIE_SECRET')
    Set-TaskEnv 'DEEPSEEK_API_KEY' (Container-Value $containers['worker'] 'DEEPSEEK_API_KEY')
    Set-TaskEnv 'DATABASE_PASSWORD' (Container-Value $containers['api'] 'DATABASE_PASSWORD')
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed' }
    $active = docker exec "${project}-postgres-1" psql -U rehearsal -d trade_fresh_acceptance -Atc "SELECT count(*) FROM ai_runs WHERE status IN ('PENDING','RUNNING');"
    if ($LASTEXITCODE -ne 0 -or "$active".Trim() -ne '0') { throw 'AI work active or unknown' }
    $stopped = $true
    docker stop "${project}-api-1" "${project}-worker-1" "${project}-worker-beat-1"
    if ($LASTEXITCODE -ne 0) { throw 'Could not pause writers' }
    docker run --rm --network "${project}_default" --entrypoint python `
        --mount 'type=bind,source=D:\work\foreign_trade\apps\api,target=/app/apps/api,readonly' `
        --workdir /app/apps/api -e PYTHONPATH=/app/apps/api `
        -e DATABASE_HOST=trade-fresh-acceptance-postgres-1 `
        -e DATABASE_NAME=trade_fresh_acceptance -e DATABASE_USER=rehearsal -e DATABASE_PASSWORD `
        trade-fresh-acceptance-api:search-0035-20260908 scripts/deploy_company_search_0035.py
    if ($LASTEXITCODE -ne 0) { throw 'Guarded migration failed; do not rerun without inspection' }
    & docker @composeArgs up -d --no-deps --no-build api worker worker-beat web
    if ($LASTEXITCODE -ne 0) { throw 'Runtime update incomplete; inspect before retrying' }
    $updatedWeb = Read-Container "${project}-web-1"
    foreach ($key in @('LOGTO_APP_SECRET', 'LOGTO_COOKIE_SECRET', 'LOGTO_APP_ID', 'APP_BASE_URL')) {
        if ((Container-Value $updatedWeb $key) -cne (Container-Value $containers['web'] $key)) {
            throw 'Identity configuration changed unexpectedly'
        }
    }
    $updatedWorker = Read-Container "${project}-worker-1"
    if ((Container-Value $updatedWorker 'AI_PROVIDER') -ne 'deepseek' -or
        (Container-Value $updatedWorker 'DEEPSEEK_MODEL') -ne 'deepseek-v4-pro' -or
        (Container-Value $updatedWorker 'DEEPSEEK_API_KEY') -cne $env:DEEPSEEK_API_KEY) {
        throw 'Model configuration changed unexpectedly'
    }
    $stopped = $false
    Write-Output 'Local0035 deployment applied; health and session acceptance still required.'
} finally {
    if ($stopped) {
        # Additive index migration remains compatible with the previous running images.
        docker start "${project}-api-1" "${project}-worker-1" "${project}-worker-beat-1"
    }
    foreach ($key in $previousEnv.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnv[$key], 'Process')
    }
}
