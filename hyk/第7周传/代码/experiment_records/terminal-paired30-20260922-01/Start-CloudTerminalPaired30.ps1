$ErrorActionPreference = 'Stop'
$root = '/mnt/lizh639/terminal-paired30-20260922-01'
$python = "$root/runtime/bin/python"
$helper = "$root/control/remote_terminal_pair.py"
$arms = @(
    @{ Host = 'cubestudio_container'; Method = 'bestfgs' },
    @{ Host = 'cubestudio_container2'; Method = 'raw' }
)
$deepseekSecret = Read-Host 'DeepSeek API Key (hidden)' -AsSecureString
$daytonaSecret = Read-Host 'Daytona API Key (hidden)' -AsSecureString
$deepseekPointer = [IntPtr]::Zero
$daytonaPointer = [IntPtr]::Zero
try {
    $deepseekPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($deepseekSecret)
    $daytonaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($daytonaSecret)
    $deepseekKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($deepseekPointer).Trim()
    $daytonaKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($daytonaPointer).Trim()
    if (-not $deepseekKey -or $deepseekKey -match '\s') { throw 'Invalid DeepSeek key; nothing started.' }
    if (-not $daytonaKey -or $daytonaKey -match '\s') { throw 'Invalid Daytona key; nothing started.' }
    $payload = @{ deepseek_key = $deepseekKey; daytona_key = $daytonaKey } | ConvertTo-Json -Compress
    foreach ($arm in $arms) {
        Write-Host ("Launching {0} on {1}..." -f $arm.Method, $arm.Host)
        $remote = "$python $helper launch --method $($arm.Method)"
        $payload | & ssh -o BatchMode=yes -o ConnectTimeout=15 $arm.Host $remote
        if ($LASTEXITCODE -ne 0) {
            throw ("{0} did not confirm launch. Do not rerun blindly; use Check-CloudTerminalPaired30.ps1." -f $arm.Method)
        }
    }
    Write-Host 'Both arms are running in cloud tmux. Keep the Cube containers alive; the PC may be shut down.'
} finally {
    if ($deepseekPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($deepseekPointer) }
    if ($daytonaPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($daytonaPointer) }
    $deepseekKey = $null
    $daytonaKey = $null
    $payload = $null
    if ($deepseekSecret) { $deepseekSecret.Dispose() }
    if ($daytonaSecret) { $daytonaSecret.Dispose() }
}
