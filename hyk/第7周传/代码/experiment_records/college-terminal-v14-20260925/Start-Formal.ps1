$ErrorActionPreference = 'Stop'
$key = Read-Host 'DeepSeek API Key (hidden)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $plain | ssh -i "$env:USERPROFILE\.ssh\cubestudio_notebook" -o BatchMode=yes lizh639@172.16.108.236 "cd ~/terminalbench-v14-setup && ./runtime/bin/python launch_formal.py"
    if ($LASTEXITCODE -ne 0) { throw 'Remote launch failed; inspect the message above. Do not rerun if it says the worker is active.' }
} finally {
    if ($null -ne $plain) { $plain = $null }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
