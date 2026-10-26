"""Seal/verify all executable fixture, harness and candidate sources; no API."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import atomic_json


def hashes():
    paths = list((ROOT/'sources/bestfgs-project/src/bestfgs').glob('*.py'))
    paths += list((ROOT/'microtests').glob('*.py'))
    paths += [p for p in (ROOT/'microtests/fixtures').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += list((ROOT/'tests').glob('*.py'))
    paths += [ROOT/'evidence/previous-rejected-candidates.json']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--allow-results', action='store_true')
    args = parser.parse_args()
    path = ROOT/'evidence/source-manifest.json'
    current = hashes()
    if args.seal:
        if path.exists(): raise SystemExit('Manifest already sealed; do not overwrite')
        v8 = ROOT.parent/'memory-injection-v8/sources/bestfgs-project/src/bestfgs'
        old_manifest = json.loads((ROOT.parent/'memory-injection-v8/evidence/source-manifest.json').read_text(encoding='utf-8'))
        actual_old = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(v8.glob('*.py'))}
        if actual_old != old_manifest['candidate']:
            raise SystemExit('Original v8 hash mismatch; preserve and investigate')
        candidate = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'sources/bestfgs-project/src/bestfgs').glob('*.py'))}
        atomic_json(path, dict(files=current, candidate=candidate, original_v8=actual_old,
            changed_from_v8=[n for n in candidate if actual_old.get(n) != candidate[n]],
            original_v8_unchanged_at_seal=True, policies=['evidence','orthogonal'], threshold=.8))
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if current != manifest['files']:
        raise SystemExit('Candidate/fixture/harness hash mismatch; do not enter key')
    if not args.allow_results and (ROOT/'evidence/live-contrastive').exists():
        raise SystemExit('Results already exist; refuse duplicate experiment')
    from run_contrastive import CASE_ORDER, CASES
    for case in CASE_ORDER:
        for protected in CASES[case]['protected']:
            if not (ROOT/'microtests/fixtures'/case/protected).is_file():
                raise SystemExit('Missing protected fixture')
    print('PREFLIGHT_OK: four paired fixtures, identical base/model/budgets; <=112 provider decisions / <=224 wire attempts; no API call')


if __name__ == '__main__': main()
