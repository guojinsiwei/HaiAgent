$ErrorActionPreference = 'Stop'
$haiPython = $env:HAI_PYTHON
if (-not $haiPython) {
    $haiBundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $haiBundled) { $haiPython = $haiBundled }
    else { $haiPython = (Get-Command python -ErrorAction Stop).Source }
}
$haiPreviousPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    & $haiPython -B -m haiagent @args
    $haiExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $haiPreviousPath
}
exit $haiExitCode
