param([switch]$Apply)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Default is preflight only. No migration, build, orphan removal or provider invocation.
$project = 'trade-fresh-acceptance'
$composeArgs = @('compose', '-p', $project, '-f', 'docker-compose.yml',
    '-f', 'infra/docker/fresh.compose.yml', '-f', 'infra/docker/identity-acceptance.compose.yml',
    '-f', 'infra/docker/acceptance-storage.compose.yml', '-f', 'infra/docker/deepseek-acceptance.compose.yml',
    '-f', 'infra/docker/release-0035.compose.yml', '-f', 'infra/docker/owner-ports.compose.yml')
$expectedSource = @{
    api = 'sha256:1da4ade3822607f541a5fea3e716b5a35151cb2eed7b68902f699b69343920d5'
    worker = 'sha256:9f630af03f40d797c1b1548e1b433add8683d66d98a45f7b63cec61cd9a650d2'
    'worker-beat' = 'sha256:9f630af03f40d797c1b1548e1b433add8683d66d98a45f7b63cec61cd9a650d2'
}
$expectedTarget = @{
    api = 'sha256:1988a4285fce5779d97791c474101b459bcba809648935f65a90b8a64c06f684'
    worker = 'sha256:04bcd3993524e7bd9bdc1b196e6fedbcb10632e846cd3096dc46604bc641eeab'
    'worker-beat' = 'sha256:04bcd3993524e7bd9bdc1b196e6fedbcb10632e846cd3096dc46604bc641eeab'
}
$previousEnv = @{}

function Read-Service([string]$service) {
    $rows = @(docker inspect "${project}-${service}-1" | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or $rows.Count -ne 1) { throw 'Service unavailable' }
    $row = $rows[0]
    if ($row.Config.Labels.'com.docker.compose.project' -ne $project -or
        $row.Config.Labels.'com.docker.compose.service' -ne $service -or
        -not $row.State.Running) { throw 'Unexpected service identity or state' }
    return $row
}

function Copy-Setting($container, [string]$source, [string]$destination) {
    $values = @($container.Config.Env | Where-Object { $_.StartsWith("${source}=") })
    if ($values.Count -ne 1) { throw 'Required setting unavailable' }
    $value = $values[0].Split('=', 2)[1]
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'Required setting empty' }
    $previousEnv[$destination] = [Environment]::GetEnvironmentVariable($destination, 'Process')
    [Environment]::SetEnvironmentVariable($destination, $value, 'Process')
}

function Assert-IdleSchema {
    $result = @(docker exec "${project}-postgres-1" psql -U rehearsal -d trade_fresh_acceptance -qAtc "BEGIN READ ONLY; SELECT count(*) FROM ai_runs WHERE status IN ('PENDING','RUNNING'); SELECT version_num FROM alembic_version; COMMIT;")
    if ($LASTEXITCODE -ne 0 -or $result.Count -ne 2 -or
        $result[0] -ne '0' -or $result[1] -ne '20260908_0035') {
        throw 'Expected idle AI and schema0035; no deployment permitted'
    }
}

function Read-BusinessFingerprint {
    # Same explicitly bounded commercial/file preservation check as the preceding deployment.
    $tables = @('companies', 'contacts', 'leads', 'opportunities', 'inquiries', 'quotations',
        'quotation_versions', 'quotation_items', 'sales_orders', 'sales_order_items',
        'purchase_orders', 'purchase_order_items', 'shipments', 'shipment_items',
        'documents', 'document_versions', 'document_links', 'receivables', 'payments',
        'payment_allocations', 'customs_declarations', 'tax_refund_cases')
    $parts = foreach ($table in $tables) {
        "SELECT '$table' AS name, count(*) AS rows, md5(coalesce(string_agg(row_to_json(r)::text, '' ORDER BY r.id), '')) AS digest FROM public.$table r"
    }
    $sql = 'BEGIN READ ONLY; SELECT md5(jsonb_agg(v ORDER BY name)::text) FROM (' +
        ($parts -join ' UNION ALL ') + ') v; COMMIT;'
    $result = docker exec "${project}-postgres-1" psql -U rehearsal -d trade_fresh_acceptance -qAtc $sql
    if ($LASTEXITCODE -ne 0 -or "$result" -notmatch '^[a-f0-9]{32}$') { throw 'Fingerprint unavailable' }
    return "$result"
}

try {
    if ((Resolve-Path '.').Path -ne 'D:\work\foreign_trade') { throw 'Wrong workspace' }
    $original = @{}
    foreach ($service in @('api', 'worker', 'worker-beat', 'web', 'postgres', 'redis', 'minio')) {
        $original[$service] = Read-Service $service
    }
    foreach ($service in $expectedSource.Keys) {
        if ($original[$service].Image -ne $expectedSource[$service]) {
            throw 'Unexpected source image; inspect rather than rerun'
        }
    }
    Assert-IdleSchema
    Copy-Setting $original['web'] 'LOGTO_APP_SECRET' 'ACCEPTANCE_LOGTO_APP_SECRET'
    Copy-Setting $original['web'] 'LOGTO_COOKIE_SECRET' 'ACCEPTANCE_LOGTO_COOKIE_SECRET'
    Copy-Setting $original['worker'] 'DEEPSEEK_API_KEY' 'DEEPSEEK_API_KEY'
    Copy-Setting $original['api'] 'DATABASE_PASSWORD' 'DATABASE_PASSWORD'
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Configuration invalid' }
    # Expanded configuration stays in process memory: never print or persist it.
    $proposed = (& docker @composeArgs config --format json | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw 'Configuration inspection failed' }
    foreach ($service in $original.Keys) {
        $environmentProperty = $proposed.services.$service.PSObject.Properties['environment']
        if ($null -eq $environmentProperty) { continue }
        foreach ($setting in $environmentProperty.Value.PSObject.Properties) {
            $pair = $setting.Name + '=' + [string]$setting.Value
            if ($original[$service].Config.Env -cnotcontains $pair) {
                throw 'Proposed environment differs; no deployment permitted'
            }
        }
    }
    foreach ($service in $expectedTarget.Keys) {
        $image = docker image inspect $proposed.services.$service.image --format '{{.Id}}'
        if ($LASTEXITCODE -ne 0 -or $image -ne $expectedTarget[$service]) {
            throw 'Unexpected candidate image'
        }
    }
    $before = Read-BusinessFingerprint
    if (-not $Apply) {
        Write-Output 'Preflight passed: exact images, idle AI, schema0035, proposed environments and bounded fingerprint available. No services changed.'
        return
    }
    Assert-IdleSchema
    & docker @composeArgs up -d --no-deps --no-build api worker worker-beat
    if ($LASTEXITCODE -ne 0) { throw 'Update failed; inspect partial state before any retry' }
    foreach ($service in $original.Keys) {
        $updated = Read-Service $service
        if ($expectedTarget.ContainsKey($service)) {
            if ($updated.Image -ne $expectedTarget[$service]) { throw 'Running image mismatch' }
            if (Compare-Object ($original[$service].Config.Env | Sort-Object) ($updated.Config.Env | Sort-Object) -CaseSensitive) {
                throw 'Runtime environment changed unexpectedly'
            }
        } elseif ($updated.Id -ne $original[$service].Id) {
            throw 'Unrelated service recreated'
        }
    }
    if ((Read-BusinessFingerprint) -ne $before) { throw 'Business records changed; investigate' }
    Assert-IdleSchema
    Write-Output 'Three images updated; exact runtime environments, four unrelated containers and22commercial/file fingerprints unchanged. Postdeploy health and broker verification still required.'
} finally {
    foreach ($key in $previousEnv.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnv[$key], 'Process')
    }
}
