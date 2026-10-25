$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Experiment mail notification - secure QQ SMTP authorization'
$mailCampaign='/var/tmp/longcli-dh-tools-context-repair-20261008'
$mailPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$mailSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$mailHost='lizh639@172.16.108.236'
try {
    Write-Host 'Notify 5417779@qq.com when this experiment ends or terminates. No model API calls.'
    Write-Host 'Enter your QQ SMTP authorization code, NOT your mailbox password or DeepSeek key.'
    $mailSender=Read-Host 'QQ sender address (Enter = 5417779@qq.com)'
    if (-not $mailSender) { $mailSender='5417779@qq.com' }
    $mailSecret=Read-Host 'QQ SMTP authorization code (hidden)' -AsSecureString
    $mailPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($mailSecret)
    try {
        $mailPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($mailPointer).Trim()
        if (-not $mailPlain -or $mailPlain -match '\s') { throw 'Invalid authorization code.' }
        $mailPayload=@{sender=$mailSender;authorization_code=$mailPlain} | ConvertTo-Json -Compress
        $mailPayload | & ssh -i $mailSshKey -o BatchMode=yes -o ConnectTimeout=15 $mailHost "$mailPython -B $mailCampaign/experiment_mail.py --root $mailCampaign --detach"
        if ($LASTEXITCODE -ne 0) { throw 'Notification setup failed; not enabled.' }
        Write-Host 'Mail watcher started on compute node. SMTP acceptance does not guarantee inbox delivery.'
    } finally {
        $mailPayload=$null;$mailPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($mailPointer);$mailSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
