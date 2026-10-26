import hashlib,json,re
from pathlib import Path
from experiment import validate_protocol
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
validate_protocol(ROOT)
results=[json.loads((ROOT/f'accept-{a}.json').read_text()) for a in ('native-kz','kz-dsh','dsh')]
assert all(r['engineering_clean'] and r['exit_code']==0 and r['paid_calls']==0 for r in results)
testlog=(ROOT/'dsh-tests.log').read_text()
assert '# tests 420' in testlog and '# pass 417' in testlog and '# fail 3' in testlog
failed=re.findall(r'^not ok \d+ - (.*)$',testlog,re.M)
assert len(failed)==3 and all(x.startswith(('proof is bound','R5 exploration:')) for x in failed)
assert '# fail 0' in (ROOT/'fixture-recheck.log').read_text() and '# tests 34' in (ROOT/'fixture-recheck.log').read_text()
assert '# fail 0' in (ROOT/'transport-tests.log').read_text() and '# tests 21' in (ROOT/'transport-tests.log').read_text()
assert 'Ran 41 tests' in (ROOT/'native-tests.log').read_text() and (ROOT/'native-tests.log').read_text().rstrip().endswith('OK')
files=[p for p in ROOT.iterdir() if p.suffix in ('.py','.mjs')]
files += [ROOT/n for n in ('experiment.json','tasks.json','history.json','protocol.json','budget-profile.json','runtime-final.tar.gz','native-runtime.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz','verifier-deps-provenance.json','dsh-tests.log','fixture-recheck.log','transport-tests.log','native-tests.log')]
files += [ROOT/f'accept-{a}.json' for a in ('native-kz','kz-dsh','dsh')]
(ROOT/'source-lock.json').write_text(json.dumps(dict(files={p.relative_to(ROOT).as_posix():sha(p) for base in [ROOT/'native',ROOT/'runtime/kz/src'] for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'test-tmp' not in p.parts}),indent=2))
files.append(ROOT/'source-lock.json')
(ROOT/'ready.json').write_text(json.dumps(dict(passed=True,paid_calls=0,revision='orthogonal-learning-on-repaired-release-20261017',validation='420 JS cases: 417 passed initially; three old exploration fixtures updated to new contract, all 34 in their suites passed on recheck; 41 native, 21 transport, 8 ledger/queue; three keyless official lifecycles passed',files={p.relative_to(ROOT).as_posix():sha(p) for p in files}),indent=2))
from campaign import precheck
precheck()
from collections import Counter
print(Counter(str(t['environment'].get('storage')) for t in json.loads((ROOT/'tasks.json').read_text())['tasks']))
