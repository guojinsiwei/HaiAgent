$Host.UI.RawUI.WindowTitle = 'KZ DSH REPAIR5 - 3 tasks - secure TaoToken input'
& 'C:\Users\54177\AppData\Local\Programs\Python\Python313\python.exe' (Join-Path $PSScriptRoot 'secure_start.py')
if ($LASTEXITCODE -ne 0) { Read-Host 'Not started or needs attention. Press Enter to close' }
