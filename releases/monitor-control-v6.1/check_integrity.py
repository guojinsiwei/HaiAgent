"""Read-only cloud release and sealed experiment integrity check."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*.py'))}

assert hashes(ROOT/'sources')==json.loads((ROOT/'fixed-source-manifest.json').read_text())
assert hashes(ROOT/'integration')==json.loads((ROOT/'integration-source-manifest.json').read_text())
for row in json.loads((ROOT/'baseline-manifest.json').read_text()):
    assert hashlib.sha256(Path(row['origin']).read_bytes()).hexdigest()==row['sha256'], row['path']
experiment=Path('/var/tmp/lizh639-lhtb-v6-v7-paired8-20260930')
sealed=json.loads((experiment/'release-source-verification.json').read_text())
for arm in ('v6','v7'):
    assert hashes(experiment/'arms'/arm)==sealed[arm]['hashes'], arm
print(json.dumps(dict(repair_sources_verified=True,original_v6_verified=True,
                     sealed_experiment_arms_verified=['v6','v7'],model_calls=0)))
