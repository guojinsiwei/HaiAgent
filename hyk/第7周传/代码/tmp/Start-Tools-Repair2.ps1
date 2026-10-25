$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH tools REPAIR2 + keep no-tools running - secure input'
try {
    Write-Host 'Keep existing no-tools tasks/results. Restart ONLY tools group: fresh20, same small budget, 6 concurrent.'
    Write-Host 'Tools start only after acceptance. NO EMAIL. Key stays in RAM and SSH stdin only.'
    $repairSecret=Read-Host 'DeepSeek API key (hidden; never send in chat)' -AsSecureString
    $repairPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($repairSecret)
    try {
        $repairPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($repairPointer).Trim()
        if(-not $repairPlain -or $repairPlain -match '\s'){throw 'Empty or invalid credential'}
        $repairPlain | ssh -i C:/Users/54177/.ssh/cubestudio_notebook -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /mnt/sdb/home/lizh639/dh-tools-output-repair2-ops/launch_tools_repair_handoff.py'
        if($LASTEXITCODE -ne 0){throw 'Launch uncertain; inspect before retry'}
    } finally {
        $repairPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($repairPointer)
        $repairSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
