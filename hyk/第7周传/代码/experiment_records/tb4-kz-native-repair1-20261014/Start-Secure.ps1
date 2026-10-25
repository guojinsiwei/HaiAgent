$ErrorActionPreference='Stop'
& 'C:\Users\54177\AppData\Local\Programs\Python\Python313\python.exe' "$PSScriptRoot\secure_start.py"
if($LASTEXITCODE -ne 0){Write-Host 'Not started. Read precheck failure above; do not paste a key into this window.'}
Read-Host 'Press Enter to close'
