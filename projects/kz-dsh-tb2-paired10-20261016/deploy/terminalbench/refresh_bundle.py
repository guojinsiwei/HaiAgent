"""Refresh an unlaunched candidate, invalidate readiness and record exact source."""
import hashlib,json,shutil,tarfile
from pathlib import Path
from build_runtime import build
ROOT=Path(__file__).resolve().parent
assert not (ROOT/'launch-once.marker').exists(),'Never mutate a launched experiment'
(ROOT/'ready.json').write_text(json.dumps(dict(passed=False,reason='candidate refresh; acceptance required')))
with tarfile.open(ROOT/'source.tar.gz') as archive:archive.extractall(ROOT/'runtime/kz',filter='data')
for name in ('container-run.mjs','deadline.mjs','provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','shared-budget.mjs'):
    shutil.copyfile(ROOT/name,ROOT/'runtime/kz'/name)
build()
protocol=json.loads((ROOT/'protocol.json').read_text())
protocol['source_sha256']=hashlib.sha256((ROOT/'source.tar.gz').read_bytes()).hexdigest()
assert protocol['tasks_sha256']==hashlib.sha256((ROOT/'tasks.json').read_bytes()).hexdigest()
for name in protocol['common_hashes']:
    protocol['common_hashes'][name]=hashlib.sha256((ROOT/'runtime/kz'/name).read_bytes()).hexdigest()
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
print('Unlaunched candidate refreshed; model calls: 0')
