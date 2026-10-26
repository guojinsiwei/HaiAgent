param()
$ErrorActionPreference='Stop'
$monitorRoot=$PSScriptRoot
$monitorPython='C:\Users\54177\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
if (-not (Test-Path -LiteralPath $monitorPython)) { throw 'Python windowed runtime missing.' }
$monitorDesktop=[Environment]::GetFolderPath('Desktop')
$monitorShortcut=Join-Path $monitorDesktop '实验进度.lnk'
$monitorShell=New-Object -ComObject WScript.Shell
$monitorLink=$monitorShell.CreateShortcut($monitorShortcut)
$monitorLink.TargetPath=$monitorPython
$monitorLink.Arguments='"'+(Join-Path $monitorRoot 'app.pyw')+'"'
$monitorLink.WorkingDirectory=$monitorRoot
$monitorLink.Description='实时查看 CubeStudio 和学院计算节点实验进度'
$monitorIcon=Join-Path $monitorRoot 'monitor.ico'
if (Test-Path -LiteralPath $monitorIcon) { $monitorLink.IconLocation=$monitorIcon }
$monitorLink.Save()
Write-Output $monitorShortcut
