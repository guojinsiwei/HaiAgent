$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$reportDir = Join-Path $projectRoot 'audit'
New-Item -ItemType Directory -Force $reportDir | Out-Null
$image = 'longcli-audit/make-pytest:2015f37'
$imageId = docker image inspect $image --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Existing offline image unavailable; no pull attempted' }
$checks = @()
foreach ($index in @(1,2)) {
  $containerName = 'dsh-baseline-isolation-' + [guid]::NewGuid().ToString('N')
  $result = docker run --rm --name $containerName --network none --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 8g --pids-limit 256 --tmpfs /tmp --tmpfs /workspace --tmpfs /home/task -e HOME=/home/task -w /workspace $imageId sh -c 'test ! -e /workspace/from-other-task && test ! -e /home/task/memory.json && echo task-local > /workspace/from-other-task && echo local-memory > /home/task/memory.json && echo isolated'
  if ($LASTEXITCODE -ne 0 -or $result -ne 'isolated') { throw "Isolation check failed: $containerName" }
  $checks += @{name=$containerName; network='none'; freshWorkspace=$true; freshHome=$true; result=$result}
}
@{image=$image;imageId=$imageId;checks=$checks;passed=$true;dshLifecycleInsideLinux=$false;reason='Cached image has no Node and no pydantic. DSH lifecycle is tested separately on Windows.';paidApiCalls=0} | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $reportDir 'container-isolation.json')
Write-Output '2 fresh offline containers passed workspace/home isolation; no Linux DSH lifecycle claim.'
