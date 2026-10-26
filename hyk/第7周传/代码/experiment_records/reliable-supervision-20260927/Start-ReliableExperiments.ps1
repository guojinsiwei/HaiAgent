$ErrorActionPreference = 'Stop'
$remote = 'lizh639@172.16.108.236'
$sshArgs = @('-i', "$env:USERPROFILE\.ssh\cubestudio_notebook", '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', $remote)
$secret = Read-Host 'DeepSeek API Key (hidden; resume only the 19 unstarted LHTB trials)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key input' }
    $plain | & ssh @sshArgs '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /mnt/sdb/home/lizh639/reliable-supervision-v2/launch_v2.py /var/tmp/lizh639-lhtb-r4 college'
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed; inspect state before retrying.' }
} finally {
    $plain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
