$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$auditDir=Join-Path $projectRoot 'audit/linux'
New-Item -ItemType Directory -Force $auditDir | Out-Null
$environment=Get-Content -Raw (Join-Path $projectRoot 'environment-lock.json') | ConvertFrom-Json
$image=$environment.image
$imageId=docker image inspect $environment.imageId --format '{{.Id}}'
if($LASTEXITCODE -ne 0){throw 'Linux image not built; no automatic pull'}
if($imageId -ne $environment.imageId){throw 'Linux image differs from environment lock'}
$runs=@()
$cases=@(
  @{name='native';pattern='native DSH lifecycle'},
  @{name='recuris';pattern='Recuris W, retrieval'},
  @{name='taco';pattern='TACO planner compresses'},
  @{name='regression';pattern=''}
)
foreach($case in $cases){
  $name='dsh-baseline-'+$case.name+'-'+[guid]::NewGuid().ToString('N')
  $args=@('run','--rm','--name',$name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--cpus','2','--memory','8g','--pids-limit','256','--tmpfs','/tmp','--tmpfs','/root','--tmpfs','/opt/baselines/dsh-baselines/.runtime','--env','HOME=/root',$imageId,'node','--test','--test-reporter=tap')
  if($case.pattern){$args+=@('--test-name-pattern',$case.pattern,'tests/lifecycle.test.mjs')}
  else{$args+=@('tests/lifecycle.test.mjs','tests/edge.test.mjs','tests/official-wire.test.mjs')}
  $output=& docker @args 2>&1
  $code=$LASTEXITCODE
  $output | Set-Content -Encoding utf8 (Join-Path $auditDir ($case.name+'.tap'))
  $runs+=@{case=$case.name;container=$name;exitCode=$code;freshWorkspace=$true;freshHome=$true;network='none'}
  Write-Output ($case.name+': '+$code)
}
@{image=$image;imageId=$imageId;runs=$runs;passed=(@($runs|Where-Object {$_.exitCode -ne 0}).Count -eq 0);realModelApiCalls=0;api='localhost fixture inside each fresh container';linuxDshLifecycle=$true} | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $auditDir 'results.json')
if(@($runs|Where-Object {$_.exitCode -ne 0}).Count -ne 0){exit 1}
