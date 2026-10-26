param(
    [string]$Bundle = "$env:USERPROFILE\Downloads\evaluation-bundle.zip",
    [string]$RemoteHost = "",
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$python = (Get-Command py -ErrorAction Stop).Source
$arguments = @('-3', (Join-Path $PSScriptRoot 'evaluate_swe_batch.py'), '--bundle', $Bundle,
    '--output-root', (Join-Path $PSScriptRoot 'benchmark_results\notebook-official'), '--workers', '1')
if ($RemoteHost) { $arguments += @('--ssh-host', $RemoteHost) }
if ($Offline) { $arguments += '--offline' }
$docker = (Get-Command docker -ErrorAction Stop).Source
function Test-DockerReady {
    # Windows PowerShell may turn native stderr into a terminating error.
    $ErrorActionPreference = 'Continue'
    & $docker info --format '{{.ServerVersion}}' *> $null
    return ($LASTEXITCODE -eq 0)
}
if (-not (Test-DockerReady)) {
    Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 4
        if (Test-DockerReady) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Docker did not become ready. Open Docker Desktop and inspect its status.' }
}
& $python @arguments
exit $LASTEXITCODE
