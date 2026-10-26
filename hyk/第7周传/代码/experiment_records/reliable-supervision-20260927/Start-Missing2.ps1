$ErrorActionPreference = 'Stop'
$remote = 'lizh639@172.16.108.236'
$sshArgs = @('-i', "$env:USERPROFILE\.ssh\cubestudio_notebook", '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', $remote)
$secret = Read-Host 'DeepSeek API Key (hidden; two predeclared replacement trials)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key input' }
    $plain | & ssh @sshArgs '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /var/tmp/lizh639-lhtb-missing2-r5/launch_missing2.py'
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed; inspect status before retrying.' }
} finally {
    $plain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
