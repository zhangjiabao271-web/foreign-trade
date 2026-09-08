$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Local API-only deployment: no migration, remote calls, model execution or other recreation.
$project = 'trade-fresh-acceptance'
$expectedImage = 'sha256:7f55625e034bab39ac16e2862c7de6319416828015b667c9a013c26b949b8c53'
$composeArgs = @('compose', '-p', $project, '-f', 'docker-compose.yml',
    '-f', 'infra/docker/fresh.compose.yml', '-f', 'infra/docker/identity-acceptance.compose.yml',
    '-f', 'infra/docker/acceptance-storage.compose.yml', '-f', 'infra/docker/deepseek-acceptance.compose.yml',
    '-f', 'infra/docker/release-0035.compose.yml')
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

function Read-BusinessFingerprint {
    # Fixed table allowlist; exclude asynchronous operational tables that remain live.
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
    $image = docker image inspect 'trade-fresh-acceptance-api:inquiry-port-20260909' --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $image -ne $expectedImage) { throw 'Unexpected candidate image' }
    $api = Read-Service 'api'
    $unchanged = @{}
    foreach ($service in @('web', 'worker', 'worker-beat', 'postgres', 'redis', 'minio')) {
        $unchanged[$service] = Read-Service $service
    }
    Copy-Setting $unchanged['web'] 'LOGTO_APP_SECRET' 'ACCEPTANCE_LOGTO_APP_SECRET'
    Copy-Setting $unchanged['web'] 'LOGTO_COOKIE_SECRET' 'ACCEPTANCE_LOGTO_COOKIE_SECRET'
    Copy-Setting $unchanged['worker'] 'DEEPSEEK_API_KEY' 'DEEPSEEK_API_KEY'
    Copy-Setting $api 'DATABASE_PASSWORD' 'DATABASE_PASSWORD'
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Configuration invalid' }
    $before = Read-BusinessFingerprint
    & docker @composeArgs up -d --no-deps --no-build api
    if ($LASTEXITCODE -ne 0) { throw 'API update failed; inspect before retrying' }
    $updated = Read-Service 'api'
    if ($updated.Image -ne $expectedImage) { throw 'Running image mismatch' }
    if (Compare-Object ($api.Config.Env | Sort-Object) ($updated.Config.Env | Sort-Object)) {
        throw 'API environment changed unexpectedly'
    }
    foreach ($service in $unchanged.Keys) {
        if ((Read-Service $service).Id -ne $unchanged[$service].Id) { throw 'Unrelated service recreated' }
    }
    if ((Read-BusinessFingerprint) -ne $before) { throw 'Business records changed; investigate' }
    Write-Output 'API image updated; environment and 22 business-table fingerprints unchanged. Health verification still required.'
} finally {
    foreach ($key in $previousEnv.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnv[$key], 'Process')
    }
}
