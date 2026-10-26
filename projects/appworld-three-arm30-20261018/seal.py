from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parent
assert not (R/'launch-once.marker').exists()
def read(name):return json.loads((R/name).read_text())
assert read('world-acceptance.json')['passed'] and read('entry-acceptance.json')['passed']
assert len(read('grading-preflight.json'))==30 and all(r['report']['total_count']>0 and r['report']['success'] is False for r in read('grading-preflight.json'))
assert len(read('positive-control.json'))==3 and all(r['success'] for r in read('positive-control.json'))
assert not read('authorization.json')['held_methods']
assert 'semanticReconnaissanceSteps: 8' in (R/'runtime/hld/.runtime/kz.patch.yml').read_text()
assert not list((R/'public-data').rglob('ground_truth'))
for name,value in read('source-lock.json').items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==value,name
with (R/'controller-tests.log').open('w') as log:
    subprocess.run(['python3','-m','unittest','test_bounded_ledger','test_controller','-v'],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
paths=[p for p in R.iterdir() if p.is_file() and (p.suffix in ['.py','.mjs'] or p.name in ['authorization.json','protocol.json','budget-profile.json','task-manifest.json','source-lock.json','image.json'])]
paths += [p for p in (R/'runtime').rglob('*') if p.is_file()]
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(R/'ready.json').write_text(json.dumps({'passed':True,'hashes':hashes,'model_calls_during_acceptance':0,
    'checks':['30 starter scores','3 TRAIN official positive controls','real app execution and isolated persistent worlds','saved state regrading',
      'all 4 DSH entrypoints reach denied budget lease','per-trial fault isolation and ledger limits','HLD semantic tests 27','KZDSH v2 tests 11']},indent=2))
print('SEALED_READY',len(hashes),'files; zero model calls')
