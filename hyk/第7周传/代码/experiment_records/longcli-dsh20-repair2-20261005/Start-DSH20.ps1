param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Official DeepSeek Harness - LongCLI repair2 (32K output)'
$campaign='/var/tmp/lizh639-longcli-dsh20-repair2-20261005'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
$contextTokens=1000000
Write-Host '20 NEW official DeepSeek Harness tasks. Existing DH results are not rerun.'
Write-Host 'Each task: a NEW container, NEW DSH home, NEW workspace, NEW isolated network.'
Write-Host 'DeepSeek Flash, thinking disabled, temperature 0. 800 total API attempts / 600 root tool calls / 2 hours.'
Write-Host 'Native output allowance: 32768 tokens per call. All20 tasks rerun under the same configuration.'
Write-Host "Context budget: $contextTokens tokens. Native DSH compaction. 4 parallel tasks after the first pilot."
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/check_ready.py"
if ($LASTEXITCODE -ne 0) { throw 'Keyless final acceptance failed. NO paid task started.' }
$secret=Read-Host 'DeepSeek API key (hidden; do not paste it into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch.py --check-only"
    if ($LASTEXITCODE -ne 0) { throw 'Credential/model preflight failed. NO paid task started.' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain; inspect public status before any retry.' }
    $relay=Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log') -PassThru
    Write-Host 'Controller started. Official grading is automatic on the server, even if this window closes.'
    Write-Host 'Keep the local computer online for automatic result download. Result relay uses NO model API.'
    Write-Host "Result relay PID: $($relay.Id)"
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
