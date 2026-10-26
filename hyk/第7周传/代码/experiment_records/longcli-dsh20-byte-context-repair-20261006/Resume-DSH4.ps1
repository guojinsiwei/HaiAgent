$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DSH resume: ONLY 4 never-started LongCLI tasks'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$proxy="ProxyCommand=ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p lizh639@172.16.108.236"
$remote='/mnt/lizh639/envs/swe-eval/bin/python -B /mnt/lizh639/longcli-dsh20-byte-context-repair-20261006/resume_launch.py'
Write-Host 'Resume ONLY lock/net/syscall/traps. Existing 16 attempts are NOT rerun.'
Write-Host '2 parallel on original worker 0; original model, algorithm and 800 requests / 600 tools unchanged.'
& ssh -i $sshKey -p 31081 -o BatchMode=yes -o $proxy root@172.16.108.241 "$remote --check-only"
if ($LASTEXITCODE -ne 0) { throw 'Resume preflight failed; no model call started.' }
$secret=Read-Host 'Fresh DeepSeek API key (hidden; never paste into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    $plain | & ssh -i $sshKey -p 31081 -o BatchMode=yes -o $proxy root@172.16.108.241 $remote
    if ($LASTEXITCODE -ne 0) { throw 'Resume failed or uncertain. Do NOT retry; inspect public status.' }
    Write-Host 'Remaining four tasks launched. Existing artifacts are being graded separately.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
