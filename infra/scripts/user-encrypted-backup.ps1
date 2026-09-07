# Local-user DPAPI only. No plaintext backup files, passphrases, or credential logging.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-BackupEntropy {
    param([Parameter(Mandatory)][string]$Purpose)
    return ,([Text.Encoding]::UTF8.GetBytes("trade-workbench-local-backup-v1:$Purpose"))
}

function Protect-BackupBytes {
    param([Parameter(Mandatory)][byte[]]$Bytes, [Parameter(Mandatory)][string]$Purpose)
    return ,([Security.Cryptography.ProtectedData]::Protect(
        $Bytes, (Get-BackupEntropy $Purpose), [Security.Cryptography.DataProtectionScope]::CurrentUser))
}

function Unprotect-BackupBytes {
    param([Parameter(Mandatory)][byte[]]$Bytes, [Parameter(Mandatory)][string]$Purpose)
    return ,([Security.Cryptography.ProtectedData]::Unprotect(
        $Bytes, (Get-BackupEntropy $Purpose), [Security.Cryptography.DataProtectionScope]::CurrentUser))
}

function Save-EncryptedBackup {
    param([Parameter(Mandatory)][byte[]]$Bytes, [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Purpose)
    $protected = Protect-BackupBytes $Bytes $Purpose
    $file = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $file.Write($protected, 0, $protected.Length); $file.Flush($true) }
    finally { $file.Dispose(); [Array]::Clear($protected, 0, $protected.Length) }
}

function Invoke-BackupProcess {
    param([Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments, [byte[]]$InputBytes,
        [int]$MaximumBytes = 67108864)
    # Never forward child stderr: database diagnostics may contain row contents or secrets.
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardInput = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $buffer = [byte[]]::new(65536)
    $output = [IO.MemoryStream]::new()
    $started = $false
    try {
        if (-not $process.Start()) { throw 'Could not start backup process' }
        $started = $true
        $errors = $process.StandardError.ReadToEndAsync()
        $inputTask = $null
        if ($InputBytes) {
            $inputTask = $process.StandardInput.BaseStream.WriteAsync($InputBytes, 0, $InputBytes.Length)
        } else { $process.StandardInput.Close() }
        while ($true) {
            $readTask = $process.StandardOutput.BaseStream.ReadAsync($buffer, 0, $buffer.Length)
            if ($inputTask) {
                $ready = [Threading.Tasks.Task]::WhenAny([Threading.Tasks.Task[]]@($inputTask, $readTask))
                if (-not $ready.Wait(30000)) { throw 'Backup process IO timed out' }
                if ($inputTask.IsCompleted) {
                    $null = $inputTask.GetAwaiter().GetResult()
                    $process.StandardInput.Close()
                    $inputTask = $null
                }
            }
            if (-not $readTask.Wait(30000)) { throw 'Backup process output timed out' }
            $length = $readTask.GetAwaiter().GetResult()
            if ($length -eq 0) { break }
            if ($output.Length + $length -gt $MaximumBytes) { throw 'Backup exceeds the bounded in-memory limit' }
            $output.Write($buffer, 0, $length)
        }
        if (-not $process.WaitForExit(30000)) { throw 'Backup process exit timed out' }
        $null = $errors.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "Backup subprocess failed with exit $($process.ExitCode); output withheld" }
        return ,($output.ToArray())
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        [Array]::Clear($buffer, 0, $buffer.Length)
        $segment = [ArraySegment[byte]]::new([byte[]]::new(0))
        if ($output.TryGetBuffer([ref]$segment)) {
            [Array]::Clear($segment.Array, $segment.Offset, $segment.Count)
        }
        $output.Dispose()
        $process.Dispose()
    }
}
