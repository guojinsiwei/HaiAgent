$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Server login - masked password'
$taskPython = Join-Path $PSScriptRoot '../SUZ/.venv/Scripts/python.exe'
& $taskPython (Join-Path $PSScriptRoot 'connect-masked.py')
