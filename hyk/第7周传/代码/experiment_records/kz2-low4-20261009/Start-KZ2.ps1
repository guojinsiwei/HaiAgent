$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='KZ2.0 four tasks - secure API key input'
$kzCampaign='/mnt/sdb/home/lizh639/kz2-low4-20261009'
$kzPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$kzIdentity='C:/Users/54177/.ssh/cubestudio_notebook'
try {
    Write-Host 'KZ2.0: cow / lock / mmap / cmu_p2. Four concurrent independent tasks.'
    Write-Host 'deepseek-flash, thinking OFF, temperature 0. 800 API / 600 tools / 2h per task.'
    Write-Host '32768 output, 1M context. CNY50 ceiling per task, shared across roles/retries.'
    Write-Host 'Recovery rejection hard stop REMOVED. Original results remain unchanged.'
    & ssh -i $kzIdentity -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$kzPython -B $kzCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; no model API calls allowed.' }
    $kzSecret=Read-Host 'Enter NEW DeepSeek API key (hidden; do not paste in chat)' -AsSecureString
    $kzPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($kzSecret)
    try {
        $kzPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($kzPointer).Trim()
        if (-not $kzPlain -or $kzPlain -match '\s') { throw 'Invalid credential' }
        $kzPlain | & ssh -i $kzIdentity -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$kzPython -B $kzCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect state before retrying.' }
        Write-Host 'Started KZ2.0. Official grading follows automatically.' -ForegroundColor Green
    } finally {
        $kzPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($kzPointer)
        $kzSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
