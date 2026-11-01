[CmdletBinding()]
param(
    [string]$Python = 'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
    [switch]$IncludeTorch,
    [string]$TorchCpuProxy = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Bundled Python was not found.' }
$root = $PSScriptRoot
$wheelDir = Join-Path $root 'extra-wheels'
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$runDir = Join-Path $root ('extra-download-logs/' + $stamp)
New-Item -ItemType Directory -Path $wheelDir,$runDir -Force | Out-Null
$groups = @(
    @{ name='numpy230'; requirements=@('numpy==2.3.0') },
    @{ name='numpy231-pillow'; requirements=@('numpy==2.3.1','pillow==11.2.1') },
    @{ name='pandas'; requirements=@('pandas==2.3.2') },
    @{ name='opencv-ocr'; requirements=@('opencv-python==4.11.0.86','numpy==2.3.1','pytesseract==0.3.13') },
    @{ name='rdflib'; requirements=@('rdflib==7.1.4') },
    @{ name='mujoco'; requirements=@('mujoco==3.3.5') },
    @{ name='toml-opencv-contrib'; requirements=@('toml==0.10.2','opencv-contrib-python==4.11.0.86') },
    @{ name='chess'; requirements=@('chess==1.11.2'); sourceOnly=$true; buildRequirements=@('setuptools==84.0.0','wheel==0.48.0','packaging==26.3') },
    # The official pytorch-model-cli verifier explicitly uses the CPU index and
    # unsafe-best-match; its ==2.7.1 / ==0.22.1 requirements select +cpu builds.
    @{ name='torch271-vision'; requirements=@('torch==2.7.1+cpu','torchvision==0.22.1+cpu','numpy==2.3.1','opencv-python==4.11.0.86'); large=$true; cpuIndex=$true },
    @{ name='torch270'; requirements=@('torch==2.7.0'); large=$true }
)
# pip's --platform selects wheel tags, but environment markers otherwise describe
# this Windows host. Patch only this child process's marker environment so Linux
# dependencies (including Torch's CUDA packages) are not silently omitted.
$pipDriver = @'
import sys
from pip._vendor.packaging import markers
original_environment = markers.default_environment
def target_environment():
    return dict(original_environment(), os_name="posix", sys_platform="linux",
                platform_system="Linux", platform_machine="x86_64",
                python_version="3.13", python_full_version="3.13.9",
                implementation_name="cpython", implementation_version="3.13.9",
                platform_python_implementation="CPython")
markers.default_environment = target_environment
from pip._internal.cli.main import main
raise SystemExit(main(sys.argv[1:]))
'@
$status = [ordered]@{
    started_utc=[DateTime]::UtcNow.ToString('o'); finished_utc=$null
    index='https://pypi.org/simple'; target='CPython 3.13 Linux x86_64'
    platform_tags=@('manylinux_2_28_x86_64','manylinux2014_x86_64','manylinux_2_17_x86_64',
        'manylinux2010_x86_64','manylinux_2_12_x86_64','manylinux1_x86_64','manylinux_2_5_x86_64','linux_x86_64')
    include_torch=[bool]$IncludeTorch; groups=@(); files=@(); ready=$false
}
$statusPath = Join-Path $runDir 'status.json'
function Get-OfficialMetadata([string]$Uri) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try { return Invoke-RestMethod -Uri $Uri -TimeoutSec 45 }
        catch {
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}
function Save-Status {
    $status | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    $status | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $root 'extra-download-status.json') -Encoding UTF8
    $groupFiles = [ordered]@{}
    foreach ($item in $status.groups) { $groupFiles[$item.name] = @($item.files) }
    $groupFiles | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root 'extra-groups-files.json') -Encoding UTF8
}
foreach ($group in $groups) {
    $row = [ordered]@{ name=$group.name; requirements=$group.requirements; state='pending'; exit_code=$null; log=$null; files=@() }
    if ($group.large -and -not $IncludeTorch) {
        $row.state = 'deferred_large_download'
        $status.groups += $row
        Save-Status
        continue
    }
    $logPath = Join-Path $runDir ($group.name + '.log')
    $row.log = $logPath
    $row.state = 'downloading'
    $status.groups += $row
    Save-Status
    Write-Host ('Downloading dependency group: ' + $group.name)
    $pipArgs = @('--isolated','--disable-pip-version-check','--log',$logPath,
        'download','--index-url','https://pypi.org/simple','--dest',$wheelDir,'--retries','3','--timeout','45')
    if ($group.sourceOnly) {
        # Source archive only: no host-side build, install, or source execution.
        # pip may prepare sdist metadata; download directly from official PyPI instead.
        try {
            $metadata = Get-OfficialMetadata 'https://pypi.org/pypi/chess/1.11.2/json'
            $asset = @($metadata.urls | Where-Object { $_.packagetype -eq 'sdist' })
            if ($asset.Count -ne 1) { throw 'Expected one official chess sdist.' }
            $dest = Join-Path $wheelDir $asset[0].filename
            $partial = $dest + '.partial'
            Invoke-WebRequest -Uri $asset[0].url -OutFile $partial -TimeoutSec 120
            $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $asset[0].digests.sha256) { throw 'Official chess sdist SHA256 mismatch.' }
            Move-Item -LiteralPath $partial -Destination $dest -Force
            ('Downloaded ' + $asset[0].url + "`nSHA256 " + $actual + "`nLinux wheel build still required.") |
                Set-Content -LiteralPath $logPath -Encoding UTF8
            $row.exit_code = 0
            $row.state = 'downloaded_sdist_build_required'
            $row.files = @($asset[0].filename)
            $buildLog = Join-Path $runDir 'chess-build-dependencies.log'
            $buildArgs = @('--isolated','--disable-pip-version-check','--log',$buildLog,
                'download','--index-url','https://pypi.org/simple','--dest',$wheelDir,
                '--retries','3','--timeout','45','--only-binary=:all:','--python-version','3.13',
                '--implementation','cp','--abi','cp313','--abi','abi3')
            foreach ($platform in $status.platform_tags) { $buildArgs += @('--platform',$platform) }
            $buildArgs += $group.buildRequirements
            & $Python -c $pipDriver @buildArgs 2>&1 | ForEach-Object { Write-Host ([string]$_) }
            if ($LASTEXITCODE -ne 0) { throw ('chess build-dependency download failed; see ' + $buildLog) }
            $buildFiles = @(Get-Content -LiteralPath $buildLog | Select-String '(?:Saved|File was already downloaded)\s+(.+\.whl)\s*$')
            $row.files += @($buildFiles | ForEach-Object { Split-Path -Leaf $_.Matches[0].Groups[1].Value })
            $row.files = @($row.files | Sort-Object -Unique)
            $row.build_requirements = $group.buildRequirements
        } catch {
            $row.state = 'failed'
            $row.exit_code = 1
            $_.Exception.Message | Set-Content -LiteralPath $logPath -Encoding UTF8
        }
    } else {
        $pipArgs += @('--only-binary=:all:','--python-version','3.13','--implementation','cp','--abi','cp313','--abi','abi3')
        foreach ($platform in $status.platform_tags) { $pipArgs += @('--platform',$platform) }
        if ($group.cpuIndex) {
            $pipArgs += @('--extra-index-url','https://download.pytorch.org/whl/cpu')
            if ($TorchCpuProxy) { $pipArgs += @('--proxy',$TorchCpuProxy) }
            $row.source_note = 'Official pytorch-model-cli verifier explicitly sets https://download.pytorch.org/whl/cpu with unsafe-best-match; +cpu matches its pinned public versions.'
        }
        $pipArgs += $group.requirements
        # Run each group independently, keeping incompatible pinned versions side by side.
        & $Python -c $pipDriver @pipArgs 2>&1 | ForEach-Object { Write-Host ([string]$_) }
        $row.exit_code = $LASTEXITCODE
        $row.state = if ($LASTEXITCODE -eq 0) { 'downloaded' } else { 'failed' }
        if (Test-Path -LiteralPath $logPath) {
            $saved = @(Get-Content -LiteralPath $logPath | Select-String '(?:Saved|File was already downloaded)\s+(.+\.(?:whl|tar\.gz))\s*$')
            $row.files = @($saved | ForEach-Object { Split-Path -Leaf $_.Matches[0].Groups[1].Value } | Sort-Object -Unique)
        }
    }
    Save-Status
}

# Re-check every completed archive, including reusable files from prior invocations,
# against the exact filename and SHA256 published by official PyPI.
$manifest = @()
$metadataCache = @{}
$cpuIndexCache = @{}
foreach ($file in (Get-ChildItem -LiteralPath $wheelDir -File | Where-Object { $_.Name -match '\.(whl|tar\.gz)$' } | Sort-Object Name)) {
    $parts = $file.Name -split '-'
    $package = $parts[0]
    $version = $parts[1] -replace '\.tar\.gz$',''
    $identity = $package + '/' + $version
    $entry = [ordered]@{ filename=$file.Name; package=$package; version=$version; bytes=$file.Length
        sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        official_url=$null; official_sha256=$null; verified=$false; verification_error=$null
        build_required=$file.Name.EndsWith('.tar.gz') }
    try {
        if ($version.EndsWith('+cpu') -and $package -in @('torch','torchvision')) {
            $indexUrl = 'https://download.pytorch.org/whl/cpu/' + $package + '/'
            if (-not $cpuIndexCache.ContainsKey($package)) {
                $requestArgs = @{ Uri=$indexUrl; TimeoutSec=60; UseBasicParsing=$true }
                if ($TorchCpuProxy) { $requestArgs.Proxy = $TorchCpuProxy }
                $cpuIndexCache[$package] = (Invoke-WebRequest @requestArgs).Content
            }
            $indexAssets = @([regex]::Matches($cpuIndexCache[$package], 'href="([^"]+)"') | ForEach-Object {
                $uri = [uri]::new([uri]$indexUrl, [System.Net.WebUtility]::HtmlDecode($_.Groups[1].Value))
                $filename = [uri]::UnescapeDataString(($uri.AbsolutePath -split '/')[-1])
                if ($filename -eq $file.Name) { $uri }
            })
            if ($indexAssets.Count -ne 1 -or $indexAssets[0].Fragment -notmatch '^#sha256=[0-9a-f]{64}$') {
                throw 'Exact CPU wheel SHA256 absent from the official PyTorch CPU index.'
            }
            $entry.official_url = $indexAssets[0].GetLeftPart([System.UriPartial]::Query)
            $entry.official_sha256 = $indexAssets[0].Fragment.Substring(8)
            $entry.source_note = 'CPU build required by the official pytorch-model-cli verifier index.'
        } else {
            if (-not $metadataCache.ContainsKey($identity)) {
                $metadataCache[$identity] = Get-OfficialMetadata ('https://pypi.org/pypi/' + $identity + '/json')
            }
            $asset = @($metadataCache[$identity].urls | Where-Object { $_.filename -eq $file.Name })
            if ($asset.Count -ne 1) { throw 'Exact archive filename absent from official PyPI release metadata.' }
            $entry.official_url = $asset[0].url
            $entry.official_sha256 = $asset[0].digests.sha256
        }
        $entry.verified = $entry.sha256 -eq $entry.official_sha256
        if (-not $entry.verified) { throw 'Archive SHA256 mismatch.' }
    } catch {
        $entry.verification_error = $_.Exception.Message
    }
    $manifest += $entry
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'extra-wheels-manifest.json') -Encoding UTF8
@($manifest | ForEach-Object { $_.sha256 + '  ' + $_.filename }) |
    Set-Content -LiteralPath (Join-Path $root 'extra-wheels-SHA256SUMS.txt') -Encoding ASCII
$status.files = $manifest
$status.finished_utc = [DateTime]::UtcNow.ToString('o')
$totalBytes = 0L
foreach ($entry in $manifest) { $totalBytes += [long]$entry.bytes }
$status.total_archive_bytes = $totalBytes
$status.ready = (@($status.groups | Where-Object { $_.state -ne 'downloaded' }).Count -eq 0 -and
                 @($manifest | Where-Object { -not $_.verified }).Count -eq 0)
Save-Status
Write-Host ('Archives: ' + $manifest.Count + '; bytes: ' + $status.total_archive_bytes)
Write-Host ('Status: ' + $statusPath)
if (@($status.groups | Where-Object { $_.state -eq 'failed' }).Count -gt 0 -or
    @($manifest | Where-Object { -not $_.verified }).Count -gt 0) { exit 1 }
Write-Host 'Downloads verified. Deferred Torch groups and the chess source build are explicitly recorded; this is not a complete offline readiness assertion.'
