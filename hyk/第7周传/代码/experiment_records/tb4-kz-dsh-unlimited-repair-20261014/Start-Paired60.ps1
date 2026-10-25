$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'TB4 UNLIMITED KZ vs DSH - secure TaoToken input'
& 'C:\Users\54177\AppData\Local\Programs\Python\Python313\python.exe' "$PSScriptRoot\secure_start.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Startup failed. DO NOT enter a key here. The window will close.'
    Start-Sleep -Seconds 15
    exit $LASTEXITCODE
}
