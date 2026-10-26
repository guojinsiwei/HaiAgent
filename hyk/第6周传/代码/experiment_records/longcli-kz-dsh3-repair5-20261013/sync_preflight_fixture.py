"""Repair only the preflight fixture before any credentials or paid launch."""
import json
from pathlib import Path
import shutil
import tarfile
from common import ROOT,sha,save
assert not (ROOT/'ready.json').exists() and not (ROOT/'launch-once.marker').exists() and not (ROOT/'jobs').exists()
target='tests/subgoal-integration-repair5.test.mjs'
old=json.loads((ROOT/'manifest.json').read_text())
new=json.loads((ROOT/'source-manifest.json').read_text())
changes=[n for n,h in new['files'].items() if sha(ROOT/'runtime/kz'/n)!=h]
assert changes==[target],changes
backup=ROOT/'preflight-original';backup.mkdir()
shutil.copy2(ROOT/'runtime/kz'/target,backup/'subgoal-integration-repair5.test.mjs')
shutil.copy2(ROOT/'manifest.json',backup/'manifest.json')
for name in ('regressions.tap','regressions.stderr'):
    if (ROOT/name).exists():shutil.copy2(ROOT/name,backup/name)
with tarfile.open(ROOT/'candidate.tar.gz') as archive:archive.extract(target,ROOT/'runtime/kz',filter='data')
assert sha(ROOT/'runtime/kz'/target)==new['files'][target]
old['files']['runtime/kz/'+target]=new['files'][target]
old['files']['source-manifest.json']=sha(ROOT/'source-manifest.json')
old['files']['sync_preflight_fixture.py']=sha(ROOT/'sync_preflight_fixture.py')
save(ROOT/'manifest.json',old)
save(ROOT/'preflight-repair.json',dict(reason='Linux fixture Python binary spelling',changed=[target],algorithm_changed=False,paid_api_calls=0))
print('Preflight fixture repaired; algorithm source unchanged.')
