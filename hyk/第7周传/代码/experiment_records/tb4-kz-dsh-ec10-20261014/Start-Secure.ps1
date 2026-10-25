$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'KZ DSH 0.3.0 - TB4 10 tasks - secure TaoToken input'
& 'C:\Users\54177\AppData\Local\Programs\Python\Python313\python.exe' "$PSScriptRoot\secure_start.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Precheck or startup failed. DO NOT type a key at this shell prompt.'
    Start-Sleep -Seconds 10
    exit $LASTEXITCODE
}
