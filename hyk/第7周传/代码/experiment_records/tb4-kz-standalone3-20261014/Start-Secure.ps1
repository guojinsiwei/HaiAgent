$Host.UI.RawUI.WindowTitle = 'KZ standalone 3 + native DSH resume - secure TaoToken input'
& 'C:/Users/54177/AppData/Local/Programs/Python/Python313/python.exe' (Join-Path $PSScriptRoot 'secure_start.py')
if ($LASTEXITCODE -ne 0) { Read-Host 'Not started. Press Enter to close' }
