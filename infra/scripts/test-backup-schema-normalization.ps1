Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup-schema-normalization.ps1')

function Assert-SchemaEqual([string]$Left, [string]$Right, [bool]$Expected) {
    $equal = (ConvertTo-ComparableBackupSchema $Left) -ceq (ConvertTo-ComparableBackupSchema $Right)
    if ($equal -ne $Expected) { throw 'Schema comparison regression' }
}
$arrayCast = "(ARRAY['PENDING'::character varying, 'APPROVED'::character varying])::text[]"
$elementCast = "ARRAY[('PENDING'::character varying)::text, ('APPROVED'::character varying)::text]"
$check = '    CONSTRAINT ck_example CHECK (status = ANY ({0}));'
Assert-SchemaEqual ($check -f $arrayCast) ($check -f $elementCast) $true
$index = 'CREATE INDEX idx_example ON public.examples USING btree (id) WHERE (status = ANY ({0}));'
Assert-SchemaEqual ($index -f $arrayCast) ($index -f $elementCast) $true
Assert-SchemaEqual ($check -f $arrayCast) ($check -f $elementCast.Replace('APPROVED', 'REJECTED')) $false
Assert-SchemaEqual ($index -f $arrayCast) ($index.Replace('(id)', '(other_id)') -f $elementCast) $false
Assert-SchemaEqual 'GRANT SELECT ON public.examples TO sales;' 'GRANT ALL ON public.examples TO sales;' $false
Assert-SchemaEqual 'ALTER TABLE public.examples OWNER TO manager;' 'ALTER TABLE public.examples OWNER TO sales;' $false
Assert-SchemaEqual ('SELECT ' + $arrayCast) ('SELECT ' + $elementCast) $false
Assert-SchemaEqual '-- business comment one' '-- business comment two' $false
Assert-SchemaEqual "-- Dumped by pg_dump version 18`n\restrict abc`nSELECT 1;`n\unrestrict abc" 'SELECT 1;' $true
Assert-SchemaEqual 'SELECT 1;' 'SELECT 2;' $false
Write-Output 'PASS: schema normalization and real constraint/index/ACL/owner/function/comment difference preservation (10 checks).'
