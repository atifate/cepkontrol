param([string]$SourceExeName = 'CepKontrol.exe', [switch]$ShowPairing, [switch]$EnableStartup, [switch]$Background)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$distRoot = (Resolve-Path -LiteralPath (Join-Path $workspaceRoot 'dist')).Path
$currentExe = Join-Path $distRoot 'CepKontrol.exe'
$sourceExe = Join-Path $distRoot $SourceExeName
$oldPaths = @('AcikDestek-Telefon.exe', 'AcikDestek.exe', 'AcikDestek-Dogrudan.exe', 'CepKontrol.exe') | ForEach-Object { Join-Path $distRoot $_ }
$backupRoot = Join-Path $workspaceRoot 'build\pre-pairing-binaries'
foreach ($targetPath in @($currentExe, $sourceExe, $backupRoot) + $oldPaths) {
    $absolutePath = [IO.Path]::GetFullPath($targetPath)
    if (-not $absolutePath.StartsWith($workspaceRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Target is outside the project workspace.'
    }
}
if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) { throw 'Current executable missing.' }
# Close only obsolete copies running from these exact project paths, using
# their normal window-close handler so the remote session releases its inputs.
$obsolete = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -in $oldPaths })
$sha = [System.Security.Cryptography.SHA256]::Create()
$identity = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($env:USERPROFILE)) | ForEach-Object { $_.ToString('x2') })
$sha.Dispose()
try {
    $quitSignal = [Threading.EventWaitHandle]::OpenExisting('Local\CepKontrol.' + $identity.Substring(0,20) + '.quit')
    [void]$quitSignal.Set()
    $quitSignal.Dispose()
} catch [Threading.WaitHandleCannotBeOpenedException] { }
foreach ($oldProcess in $obsolete) {
    $process = Get-Process -Id $oldProcess.ProcessId -ErrorAction SilentlyContinue
    if ($process -and $process.MainWindowHandle -ne 0) { [void]$process.CloseMainWindow() }
}
$deadline = [DateTime]::UtcNow.AddSeconds(15)
do {
    $remaining = @($obsolete | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    if ($remaining.Count -eq 0) { break }
    Start-Sleep -Milliseconds 200
} while ([DateTime]::UtcNow -lt $deadline)
if ($remaining.Count) { throw 'The obsolete application is still open; no binaries were replaced.' }
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
foreach ($oldPath in $oldPaths) {
    $backup = Join-Path $backupRoot ([IO.Path]::GetFileName($oldPath))
    if ((Test-Path -LiteralPath $oldPath) -and -not (Test-Path -LiteralPath $backup)) {
        Copy-Item -LiteralPath $oldPath -Destination $backup
    }
    if ($oldPath -ne $sourceExe) { Copy-Item -LiteralPath $sourceExe -Destination $oldPath -Force }
}
$expectedHash = (Get-FileHash -LiteralPath $currentExe).Hash
foreach ($oldPath in $oldPaths) {
    if ((Get-FileHash -LiteralPath $oldPath).Hash -ne $expectedHash) { throw 'Executable copy did not match.' }
}
$launchOptions = @{ FilePath=$currentExe; WorkingDirectory=$workspaceRoot; WindowStyle='Hidden'; PassThru=$true }
$launchArguments = @()
if ($ShowPairing) { $launchArguments += '--pair-phone' }
if ($EnableStartup) { $launchArguments += '--enable-startup' }
if ($Background) { $launchArguments += '--background' }
if ($launchArguments.Count) { $launchOptions.ArgumentList=$launchArguments }
$launched = Start-Process @launchOptions
Write-Output "Current application started (PID $($launched.Id)); both old launch paths now contain the current version."
