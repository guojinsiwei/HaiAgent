$ErrorActionPreference='Stop'
$relayPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
Write-Host 'Resume result collection only. No model calls, no worker launch, no task or grading replay.'
& $relayPython -B (Join-Path $PSScriptRoot 'relay_v2.py')
if ($LASTEXITCODE -ne 0) { Write-Host 'Collector needs attention or another collector already holds its lock. Inspect relay-error.json.' }
