param()
$ErrorActionPreference='Stop'
$campaign='/var/tmp/lizh639-longcli-retrac20-engineering-repair-20261006'
$Host.UI.RawUI.WindowTitle='Re-TRAC repair: 2 canaries first, stop batch on first engineering failure'
$remotePython="$campaign/runtime/bin/python"
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
Write-Host 'RE-TRAC repaired batch: start hog/util canaries (2 parallel), then remaining18 (4 parallel) ONLY if verified.'
Write-Host 'DeepSeek-flash, thinking off, temperature=0. 800 requests / 600 tools / 4096 output tokens / 48k input bytes.'
Write-Host 'Original recursive core; bounded compression/output adapter. 8 rollouts; fresh writable isolated task containers.'
Write-Host 'First fatal engineering fault stops new admissions AND active trials. Old results are preserved. No GPT monitoring.'
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/check_ready.py"
if ($LASTEXITCODE -ne 0) { throw 'Offline acceptance failed; no paid trial started.' }
$secret=Read-Host 'DeepSeek API key (hidden; do not paste into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py --check-only"
    if ($LASTEXITCODE -ne 0) { throw 'Credential preflight failed; no paid worker launched.' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain; do NOT rerun. Inspect public status first.' }
    Write-Host 'Submitted. Generation and automatic official grading run on the academy server; local PC can go offline.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
Read-Host 'Press Enter to close'
