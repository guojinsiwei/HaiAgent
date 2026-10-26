$Host.UI.RawUI.WindowTitle = 'KZ DSH LongCLI 3 - LARGE - secure TaoToken input'
& 'C:\Users\54177\AppData\Local\Programs\Python\Python313\python.exe' (Join-Path $PSScriptRoot 'secure_start.py')
if ($LASTEXITCODE -ne 0) { Read-Host 'Stopped before completion. Press Enter to close' }
