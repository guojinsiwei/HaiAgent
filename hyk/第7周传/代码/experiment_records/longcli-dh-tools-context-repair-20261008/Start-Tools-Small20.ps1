param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH-tools context repair SMALL budget 20 tasks - secure API key input'
$toolCampaign='/var/tmp/longcli-dh-tools-context-repair-20261008'
$toolPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$toolSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$toolHost='lizh639@172.16.108.236'
try {
    Write-Host 'DH 1342 + three code tools. ALL 20 LongCLIBench tasks. 10 concurrent after pilot.'
    Write-Host 'SMALL: 4096 output tokens; 48000 bytes input; 800 API attempts / 600 tools / 2h per task.'
    Write-Host 'All roles share the task budget. Every task has a fresh Docker workspace and memory.'
    & ssh -i $toolSshKey -o BatchMode=yes -o ConnectTimeout=15 $toolHost "$toolPython -B $toolCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; inspect before retrying.' }
    $toolSecret=Read-Host 'Enter NEW DeepSeek API key (hidden; never send it in chat)' -AsSecureString
    $toolPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($toolSecret)
    try {
        $toolPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($toolPointer).Trim()
        if (-not $toolPlain -or $toolPlain -match '\s') { throw 'Invalid credential.' }
        $toolPlain | & ssh -i $toolSshKey -o BatchMode=yes -o ConnectTimeout=15 $toolHost "$toolPython -B $toolCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect status before retrying.' }
        Write-Host 'Started on college compute node. Official grading follows automatically.' -ForegroundColor Green
    } finally {
        $toolPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($toolPointer)
        $toolSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
