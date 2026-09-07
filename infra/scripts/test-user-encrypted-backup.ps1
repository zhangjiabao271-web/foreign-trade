Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'user-encrypted-backup.ps1')
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Rejected([scriptblock]$Action) {
    $rejected = $false
    try { $null = & $Action } catch { $rejected = $true }
    Assert-True $rejected 'Expected protected operation to reject'
}
$bytes = [byte[]]::new(4096)
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$encrypted = Protect-BackupBytes $bytes 'synthetic-test'
$decrypted = Unprotect-BackupBytes $encrypted 'synthetic-test'
Assert-True ([Convert]::ToHexString($bytes) -eq [Convert]::ToHexString($decrypted)) 'Round trip failed'
Assert-Rejected { Unprotect-BackupBytes $encrypted 'wrong-purpose' }
$damaged = $encrypted.Clone()
$damaged[32] = $damaged[32] -bxor 1
Assert-Rejected { Unprotect-BackupBytes $damaged 'synthetic-test' }
$testRoot = Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'test-results'
$null = [IO.Directory]::CreateDirectory($testRoot)
$testFile = Join-Path $testRoot ("dpapi-selftest-" + [guid]::NewGuid().ToString('N') + '.dpapi')
Save-EncryptedBackup $bytes $testFile 'synthetic-test'
$before = (Get-FileHash -LiteralPath $testFile).Hash
Assert-Rejected { Save-EncryptedBackup $bytes $testFile 'synthetic-test' }
Assert-True ($before -eq (Get-FileHash -LiteralPath $testFile).Hash) 'Existing backup changed'
$readBack = Unprotect-BackupBytes ([IO.File]::ReadAllBytes($testFile)) 'synthetic-test'
Assert-True ([Convert]::ToHexString($readBack) -eq [Convert]::ToHexString($bytes)) 'File round trip failed'
$shell = (Get-Process -Id $PID).Path
$captured = Invoke-BackupProcess $shell @('-NoProfile', '-Command', '[Console]::Write("synthetic")')
Assert-True ([Text.Encoding]::UTF8.GetString($captured) -eq 'synthetic') 'Binary capture failed'
Assert-Rejected { Invoke-BackupProcess $shell @('-NoProfile', '-Command', 'exit 7') }
Assert-Rejected { Invoke-BackupProcess $shell @('-NoProfile', '-Command', '[Console]::Write("too long")') -MaximumBytes 2 }
$large = [byte[]]::new(1048576)
[Security.Cryptography.RandomNumberGenerator]::Fill($large)
$echoed = Invoke-BackupProcess $shell @('-NoProfile', '-Command', '[Console]::OpenStandardInput().CopyTo([Console]::OpenStandardOutput())') -InputBytes $large
Assert-True ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($large)) -eq [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($echoed))) 'Concurrent binary input/output failed'
[Array]::Clear($large,0,$large.Length)
[Array]::Clear($echoed,0,$echoed.Length)
foreach ($array in @($bytes, $encrypted, $decrypted, $damaged, $readBack)) { [Array]::Clear($array, 0, $array.Length) }
Write-Output 'PASS: current-user round trip, purpose binding, tamper rejection, encrypted file, overwrite refusal, process capture/failure/size guard, large duplex transfer (9 checks).'
