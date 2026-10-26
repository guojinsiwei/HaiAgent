"""Fail closed when an obsolete rejection-based task terminator returns."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def verify(root=ROOT):
    lockfile=root/'historic-config-lock.json'
    if not lockfile.exists():lockfile=ROOT.parents[1]/'experiment_records/longcli-dh-1342-complete20-20261009/KZ-config-lock.json'
    lock=json.loads(lockfile.read_text());changes=[];checked=0
    for name,expected in lock['source_hashes'].items():
        file=root/name
        if not file.exists():
            if name.startswith('sources/'):raise AssertionError('missing frozen source: '+name)
            continue
        checked+=1
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:changes.append(name)
    expected={'sources/bestfgs-project/src/bestfgs/lean_runtime.py',
              'sources/bestfgs-project/src/bestfgs/rejection_recovery.py'}
    assert set(changes)==expected,changes
    source=root/'sources/bestfgs-project/src/bestfgs'
    for forbidden in ['recovery_rejection_limit','recovery_exhausted','rejection_recovery.exhausted']:
        assert forbidden not in (source/'lean_runtime.py').read_text(),forbidden
    assert 'self.exhausted' not in (source/'rejection_recovery.py').read_text()
    assert 'hard_stop_enabled=False' in (source/'rejection_recovery.py').read_text()
    return dict(name='KZ',revision='remove-restored-rejection-hard-stop',
        verified_core_files=checked,changed_core_files=sorted(changes),
        rejection_based_task_stop=False,paid_model_calls=0)

if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False))
