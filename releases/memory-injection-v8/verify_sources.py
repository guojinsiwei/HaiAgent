"""Verify candidate hashes and prove the completed experiment source is unchanged."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]/'experiment_records/lhtb-mechanism-large-20261001/arms/common/bestfgs-project/src/bestfgs'
NEW = ROOT/'sources/bestfgs-project/src/bestfgs'


def hashes(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}


def main():
    path = ROOT/'evidence/source-manifest.json'
    baseline, candidate = hashes(BASE), hashes(NEW)
    if '--seal' in sys.argv:
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location('candidate_audit', NEW/'lean_audit.py')
        mod = module_from_spec(spec); spec.loader.exec_module(mod)
        mod.atomic_json(path, dict(baseline=baseline, candidate=candidate,
            changed=[n for n in candidate if baseline.get(n)!=candidate[n]]))
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if baseline != manifest['baseline'] or candidate != manifest['candidate']:
        raise SystemExit('source hash mismatch')
    print(json.dumps(dict(baseline_unchanged=True, candidate_verified=True,
        changed=manifest['changed']), indent=2))


if __name__ == '__main__': main()
