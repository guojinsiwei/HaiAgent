param([string]$Model='deepseek-flash')
$ErrorActionPreference='Stop'
if ($Model -notmatch '^[A-Za-z0-9._/-]+$') { throw 'Invalid model name' }
$contrastRemote='lizh639@172.16.108.236'
$contrastDirectory='/var/tmp/lizh639-contrastive-RKZKJH'
$contrastPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$contrastSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$contrastLocalResults=Join-Path $PSScriptRoot 'evidence\live-contrastive-RKZKJH'
if (Test-Path -LiteralPath $contrastLocalResults) { throw 'Results already exist; refuse overwrite or duplicate run' }
& ssh -i $contrastSshKey -o BatchMode=yes -o ConnectTimeout=15 $contrastRemote "$contrastPython -B $contrastDirectory/microtests/preflight_contrastive.py"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; key was not requested' }
Write-Host 'Four cases per arm: evidence-based contrast vs three dimensions + TF-IDF gate.'
Write-Host 'Same model and budget. Two controlled failed commands precede autonomous model decisions.'
Write-Host 'At most 112 provider decisions / 224 wire attempts. Each case has a 240-second cap.'
Write-Host 'Secret goes only through encrypted SSH stdin, not arguments, files, or logs.'
$contrastSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$contrastPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($contrastSecret)
try {
    $contrastPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($contrastPointer).Trim()
    if (-not $contrastPlain -or $contrastPlain -match '\s') { throw 'Invalid key' }
    $contrastPlain | & ssh -i $contrastSshKey -o BatchMode=yes -o ConnectTimeout=15 $contrastRemote "$contrastPython -B $contrastDirectory/microtests/run_contrastive.py --key-stdin --model $Model"
    $contrastExit=$LASTEXITCODE
} finally {
    $contrastPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($contrastPointer)
    $contrastSecret.Dispose()
}
if ($contrastExit -eq 0) {
    & ssh -i $contrastSshKey -o BatchMode=yes -o ConnectTimeout=15 $contrastRemote "$contrastPython -B $contrastDirectory/microtests/analyze_contrastive.py $contrastDirectory/evidence/live-contrastive"
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Independent audit failed; do not treat raw results as verified' }
}
& scp -r -i $contrastSshKey -o BatchMode=yes "${contrastRemote}:$contrastDirectory/evidence/live-contrastive" $contrastLocalResults
if ($LASTEXITCODE -ne 0) { throw 'Could not retrieve evidence; inspect preserved remote state before restarting' }
if ($contrastExit -ne 0) { throw "Worker stopped (exit $contrastExit); results preserved. Do not blindly restart." }
Write-Host "Completed. Results: $contrastLocalResults"
