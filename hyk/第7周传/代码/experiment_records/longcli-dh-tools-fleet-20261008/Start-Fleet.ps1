$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH three-node fleet - secure API key input - NO EMAIL'
$fleetPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$fleetScript=Join-Path $PSScriptRoot 'fleet_local.py'
try {
    & $fleetPython -B $fleetScript --check
    if ($LASTEXITCODE -ne 0) { throw 'Fleet acceptance missing; do not start.' }
    Write-Host 'Only the 10 unstarted tasks. College max8; Cube max2 each. Existing tasks/results stay intact.'
    Write-Host 'No mail account, no SMTP code. All original task budgets and algorithm unchanged.'
    $fleetSecret=Read-Host 'DeepSeek API key (hidden, do not send in chat)' -AsSecureString
    $fleetPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($fleetSecret)
    try {
        $fleetPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($fleetPointer).Trim()
        $fleetPlain | & $fleetPython -B $fleetScript
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect public status before retrying.' }
    } finally {
        $fleetPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($fleetPointer)
        $fleetSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
