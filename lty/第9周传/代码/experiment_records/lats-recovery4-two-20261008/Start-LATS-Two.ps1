param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='LATS 补跑 P0 + FS — 密钥隐藏输入'
$latsRoot='/var/tmp/lizh639-lats-recovery4-two-20261008'
$latsPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$latsSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$latsHost='lizh639@172.16.108.236'
try {
    Write-Host '只补跑 LATS 的 P0 和 FS；18 题已有评分保留。两题并发，沿用原预算。'
    & ssh -i $latsSshKey -o BatchMode=yes -o ConnectTimeout=15 $latsHost "$latsPython -B $latsRoot/launch_one.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed; no tasks started.' }
    $latsSecret=Read-Host '请在此输入 DeepSeek API key（隐藏输入，不要发到聊天中）' -AsSecureString
    $latsPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($latsSecret)
    try {
        $latsPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($latsPointer).Trim()
        if (-not $latsPlain -or $latsPlain -match '\s') { throw 'Invalid credential.' }
        $latsPlain | & ssh -i $latsSshKey -o BatchMode=yes -o ConnectTimeout=15 $latsHost "$latsPython -B $latsRoot/launch_one.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect server before retrying.' }
        Write-Host 'P0、FS 已启动；可在桌面“实验进度”查看。' -ForegroundColor Green
    } finally {
        $latsPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($latsPointer)
        $latsSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host '按 Enter 关闭窗口'
