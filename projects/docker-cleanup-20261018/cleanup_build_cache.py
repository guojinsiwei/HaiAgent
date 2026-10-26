"""Prune an explicit set of currently reclaimable, unshared, old build-cache IDs."""
import json,subprocess,re,shutil,time
from pathlib import Path
AUDIT=Path('/mnt/sdb/home/lizh639/docker-cleanup-20261018')
raw=subprocess.check_output(['docker','buildx','du','--format','json'],text=True)
rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
selected=[r for r in rows if r['Reclaimable'] is True and r['Shared'] is False and re.fullmatch('[a-z0-9]+',r['ID'])]
(AUDIT/'cache-allowlist.json').write_text(json.dumps(selected,indent=2))
before=shutil.disk_usage('/var/lib/docker').free
assert selected,'No eligible cache records'
pattern='^('+'|'.join(r['ID'] for r in selected)+')$'
command=['docker','buildx','prune','--filter','id~='+pattern,'--filter','until=24h','--force']
# Docker still checks that cache is unused at deletion time. No --all, no image/volume/container pruning.
with (AUDIT/'cache-prune.log').open('x') as log:
    p=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=600)
out=dict(finished=time.time(),exit_code=p.returncode,allowlist_count=len(selected),before_free=before,after_free=shutil.disk_usage('/var/lib/docker').free,filter='explicit reclaimable/unshared IDs AND unused for 24h')
(AUDIT/'cache-result.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
raise SystemExit(p.returncode)

