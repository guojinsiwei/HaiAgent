import hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(R/'test_scorefix.py')],check=True)
a=json.loads((R/'acceptance-scoring.json').read_text());assert a['passed']
assert len(a['results'])==10 and all(r['engineering_clean'] and r['paid_calls']==0 for r in a['results'])
# Record actual test counts so an empty/no-op verifier cannot satisfy acceptance.
for r in a['results']:
 report=json.loads((Path(r['trial'])/'verifier/ctrf.json').read_text())
 r['official_test_summary']=report['results']['summary']
assert all(r['official_test_summary']['tests']>0 for r in a['results'])
(R/'acceptance-scoring.json').write_text(json.dumps(a,indent=2))
files=[p for p in R.glob('*.py') if p.name not in ('progress.py','audit.py','inspect_more.py','recovery_inspect.py')]
files += [R/n for n in ['tasks.json','budget-profile.json','repair-plan.json','acceptance-scoring.json','runtime-final.tar.gz','native-runtime.tar.gz','python-runtime.tar.gz','recovered-submission/pipeline_parallel.py','recovered-submission/provenance.json','dependencies/network_proxy.py']]
files += list((R/'dependency-cache').glob('*/ready.json'))
digests={}
for p in files:
 with p.open('rb') as f:digests[str(p.relative_to(R))]=hashlib.file_digest(f,'sha256').hexdigest()
(R/'scorefix-seal.json').write_text(json.dumps(dict(tests_passed=True,files=digests,paid_retries=21,score_only=1,global_budget_cny=600,per_original_job_budget_cny=4,concurrency=6),indent=2))
print('SEALED')
