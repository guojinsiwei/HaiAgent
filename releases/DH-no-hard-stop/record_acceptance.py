"""Offline regression report for the no-hard-stop source candidate."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1] / 'experiment_records/longcli-dh-tools-ablation40-repair1-20261008'
tempfile.tempdir = str(ROOT / 'evidence' / 'test-temp')
Path(tempfile.tempdir).mkdir(parents=True, exist_ok=True)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

source = ROOT / 'sources/bestfgs-project/src/bestfgs'
hashes = {p.name: sha(p) for p in source.glob('*.py')}
changed = [name for name, value in hashes.items()
           if value != sha(BASE/'sources/bestfgs-project/src/bestfgs'/name)]
assert set(changed) == {'lean_runtime.py', 'rejection_recovery.py'}, changed
assert 'recovery_rejection_limit' not in (source/'lean_runtime.py').read_text()
assert 'self.exhausted' not in (source/'rejection_recovery.py').read_text()
suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
result = unittest.TextTestRunner(verbosity=0).run(suite)
report = dict(candidate='DH-no-hard-stop', observed=time.time(),
    base=str(BASE), changed_runtime_files=sorted(changed), source_hashes=hashes,
    tests=result.testsRun, passed=result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),
    skipped=[dict(test=str(test), reason=reason) for test, reason in result.skipped],
    failures=[str(test) for test, _ in result.failures], errors=[str(test) for test, _ in result.errors],
    paid_model_calls=0, deployed=False, running_experiments_changed=False,
    other_audit_findings_fixed=False, rejection_hard_stop_removed=True)
(ROOT/'evidence/acceptance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({k: report[k] for k in ('candidate','tests','passed','failures','errors',
    'changed_runtime_files','paid_model_calls','deployed')}))
raise SystemExit(0 if result.wasSuccessful() else 1)
