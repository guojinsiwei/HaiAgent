$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH no-tools supervisor REPAIR V3 - secure input'
try {
    Write-Host 'Resume no-tools only: 8 pending + 3 interrupted retries. Keep normal results and current cow. Max 6 concurrent.'
    & ssh -n -i C:/Users/54177/.ssh/cubestudio_notebook -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /mnt/sdb/home/lizh639/dh-no-tools-supervisor-v3-ops/launch_no_tools_v3.py --check'
    if($LASTEXITCODE -ne 0){throw 'Preflight failed; do not enter credential'}
    $v3Secret=Read-Host 'DeepSeek API key (hidden; do not send in chat)' -AsSecureString
    $v3Pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($v3Secret)
    try {
        $v3Plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($v3Pointer).Trim()
        if(-not $v3Plain -or $v3Plain -match '\s'){throw 'Invalid credential'}
        $v3Plain | ssh -i C:/Users/54177/.ssh/cubestudio_notebook -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /mnt/sdb/home/lizh639/dh-no-tools-supervisor-v3-ops/launch_no_tools_v3.py'
        if($LASTEXITCODE -ne 0){throw 'Launch uncertain; inspect before retry'}
    } finally {
        $v3Plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($v3Pointer)
        $v3Secret.Dispose()
    }
} catch {Write-Host $_.Exception.Message -ForegroundColor Red}
Read-Host 'Press Enter to close'
