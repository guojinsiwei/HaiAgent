$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot 'hai-novelty-screening-20260929'
$papers = @(
    @{ File = '01_MACE.pdf'; Url = 'https://arxiv.org/pdf/2609.21533' },
    @{ File = '02_Agent_Workflow_Memory.pdf'; Url = 'https://arxiv.org/pdf/2409.07429' },
    @{ File = '03_ReSum.pdf'; Url = 'https://arxiv.org/pdf/2509.13313' },
    @{ File = '04_Devils_Advocate.pdf'; Url = 'https://arxiv.org/pdf/2405.16334' },
    @{ File = '05_SWE_Search.pdf'; Url = 'https://arxiv.org/pdf/2410.20285' },
    @{ File = '06_Dream_RSI.pdf'; Url = 'https://arxiv.org/pdf/2609.14858' },
    @{ File = '07_Reflexion.pdf'; Url = 'https://arxiv.org/pdf/2303.11366' },
    @{ File = '08_ExpeL.pdf'; Url = 'https://arxiv.org/pdf/2308.10144' },
    @{ File = '09_Voyager.pdf'; Url = 'https://arxiv.org/pdf/2305.16291' },
    @{ File = '10_Hindsight.pdf'; Url = 'https://arxiv.org/pdf/2512.12818' },
    @{ File = '11_REMem.pdf'; Url = 'https://arxiv.org/pdf/2602.13530' },
    @{ File = '12_MiTa.pdf'; Url = 'https://arxiv.org/pdf/2601.22974' },
    @{ File = '13_Memory_in_the_Age_of_AI_Agents_Survey.pdf'; Url = 'https://arxiv.org/pdf/2512.13564' }
)

foreach ($paper in $papers) {
    $path = Join-Path $destination $paper.File
    & curl.exe --fail --location --retry 3 --connect-timeout 20 --max-time 300 `
        --user-agent 'Mozilla/5.0' --output $path $paper.Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $($paper.File)" }
    $stream = [System.IO.File]::OpenRead($path)
    try {
        $header = New-Object byte[] 5
        [void]$stream.Read($header, 0, 5)
    } finally {
        $stream.Dispose()
    }
    if ([Text.Encoding]::ASCII.GetString($header) -ne '%PDF-') {
        throw "Downloaded content is not a PDF: $($paper.File)"
    }
}

$manifest = foreach ($paper in $papers) {
    $path = Join-Path $destination $paper.File
    $item = Get-Item -LiteralPath $path
    [pscustomobject]@{
        file = $paper.File
        source = $paper.Url
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $destination 'manifest.json') -Encoding UTF8
Write-Output ($manifest | ConvertTo-Json -Compress)
