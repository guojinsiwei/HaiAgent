"""Revalidate Python-only changes; reuse successful unchanged JS suite evidence."""
import hashlib,json,os,re,subprocess,sys,shutil
from pathlib import Path
from validate_offline import source_hashes
ROOT=Path(__file__).resolve().parent
def main():
 before=source_hashes(ROOT/'runtime/kz');old=json.loads((ROOT/'validation.json').read_text())
 # JS source/config/tests and every deployment JS module must be byte-identical.
 related=lambda k:k.startswith('project/') or k.endswith('.mjs')
 assert {k:v for k,v in old['source_hashes'].items() if related(k)}=={k:v for k,v in before.items() if related(k)}
 reuse=[s for s in old['suites'] if s['suite'] in ('node','deadline')]
 assert {s['suite'] for s in reuse}=={'node','deadline'}
 for s in reuse:
  assert s['exit_code']==0 and s['counts'].get('tests',0)>0 and not s['counts'].get('cancelled') and not s['counts'].get('skipped')
  assert hashlib.sha256((ROOT/s['log']).read_bytes()).hexdigest()==s['log_sha256']
 shutil.copy2(ROOT/'validation.json',ROOT/'validation-before-python-recheck.json')
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(ROOT/'runtime/node/bin')+os.pathsep+os.environ.get('PATH',''))
 for k in list(env):
  if k.endswith(('API_KEY','AUTH_TOKEN')):env.pop(k,None)
 log=ROOT/'python-engineering.log'
 with log.open('w') as f:x=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT),'-p','test_*.py','-v'],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 text=log.read_text();m=re.search(r'Ran (\d+) tests?',text)
 suite=dict(suite='python',exit_code=x.returncode,counts=dict(tests=int(m.group(1)) if m else 0),log=log.name,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
 report=dict(schema_version=1,platform=sys.platform,source_hashes=before,suites=[reuse[0],suite,reuse[1]],passed=x.returncode==0 and suite['counts']['tests']>0 and before==source_hashes(ROOT/'runtime/kz'),model_acceptance=False,reuse_basis='Successful complete 396-test JS suite and18 deadline/provider tests reused only after exact related-source hash equality; all Python tests rerun')
 (ROOT/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(passed=report['passed'],suites=report['suites'])));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
