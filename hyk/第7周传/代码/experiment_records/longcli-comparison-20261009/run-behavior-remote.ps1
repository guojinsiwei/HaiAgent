param([ValidateSet('college','cube')][string]$Site='college',[string]$Method='')
$ErrorActionPreference='Stop'
$auditFolder=$PSScriptRoot
$auditSource=Get-Content -LiteralPath (Join-Path $auditFolder 'audit_behavior.py') -Raw -Encoding UTF8
$auditSource=$auditSource.Substring(0,$auditSource.LastIndexOf("if __name__=='__main__':"))
$auditSnapshot=Get-Content -LiteralPath (Join-Path $auditFolder 'public-snapshot.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Method) { $auditSnapshot.groups=@($auditSnapshot.groups | Where-Object { $_.method -eq $Method }) }
$auditPayload=@{site=$Site;snapshot=$auditSnapshot} | ConvertTo-Json -Depth 100 -Compress
$auditProgram=$auditSource+"`nimport gzip,base64`nprint(base64.b64encode(gzip.compress(json.dumps(main(json.loads(r'''"+$auditPayload+"''')),ensure_ascii=False).encode())).decode())`n"
if ($Site -eq 'college') {
    $auditProgram | ssh -i C:/Users/54177/.ssh/cubestudio_notebook -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 python3 -
} else {
    $auditProgram | ssh -i C:/Users/54177/.ssh/cubestudio_notebook -p 31081 -o BatchMode=yes -o ConnectTimeout=15 -o 'ProxyCommand=ssh -i C:/Users/54177/.ssh/cubestudio_notebook -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p lizh639@172.16.108.236' root@172.16.108.241 python3 -
}
if ($LASTEXITCODE -ne 0) { throw 'Read-only audit failed; no result inferred.' }
