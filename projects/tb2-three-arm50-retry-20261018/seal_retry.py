import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
P=R.parent/'tb2-three-arm50-20261017'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
# Verify unchanged algorithm payloads against the original packaged release.
with tarfile.open(P/'runtime-final.tar.gz') as a,tarfile.open(R/'runtime-final.tar.gz') as b:
 am={m.name:m for m in a};bm={m.name:m for m in b};assert am.keys()==bm.keys()
 for name,member in am.items():
  if name=='kz/provider-guard.mjs':continue
  assert (member.type,member.mode,member.linkname)==(bm[name].type,bm[name].mode,bm[name].linkname),name
  if member.isfile():assert a.extractfile(member).read()==b.extractfile(bm[name]).read(),name
assert sha(P/'native-runtime.tar.gz')==sha(R/'native-runtime.tar.gz')
commands=[[sys.executable,'-m','unittest','test_retry','test_bounded_ledger'],[str(P/'runtime/node/bin/node'),'--test','test-provider-guard.mjs','test_bounded_transport.mjs','test_retry_stream.mjs']]
for i,cmd in enumerate(commands):
 with (R/f'acceptance-{i}.log').open('w') as log:result=subprocess.run(cmd,cwd=R,stdout=log,stderr=log)
 assert result.returncode==0,'Acceptance failed; inspect acceptance-'+str(i)+'.log'
parent=json.loads((P/'ready.json').read_text())['files']
parent.update({'dependencies/'+k:v for k,v in json.loads((P/'dependencies/ready.json').read_text())['files'].items()})
(R/'parent-source-seal.json').write_text(json.dumps(dict(files=parent),indent=2))
protocol=dict(parent=str(P),scope='One additional attempt per engineering failure in the completed first pass',skip=['clean score 0','valid budget exhaustion','ambiguous live process ownership','insufficient original job budget'],concurrency=dict(total=3,per_arm=1),first_pass='Wait for finished and original supervisor exit',budget=dict(total_cny=600,cumulative_original_job_cny=4,shared_database=str(P/'spending.sqlite'),unknown_costs_retained=True),model='deepseek-flash',endpoint='https://api.taotoken.net/token/v1/messages',solver_seconds=2700,environment_start_seconds=1800,changes=['Official PyPI replaces rate-limited USTC PyPI mirror; bounded downloads and retries','Serial image warmup for startup-timeout tasks, 1800 seconds maximum','One bounded recovery for successful HTTP SSE missing final usage; reserve full unknown charge and new attempt separately'],algorithm_payloads_unchanged=True)
(R/'protocol.json').write_text(json.dumps(protocol,indent=2))
files=[p for p in R.iterdir() if p.suffix in ('.py','.mjs','.json') and p.name not in ('retry-seal.json','schedule.json')]
files += [R/n for n in ['runtime-final.tar.gz','native-runtime.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz','dependencies/network_proxy.py']]
(R/'retry-seal.json').write_text(json.dumps(dict(tests_passed=True,files={str(p.relative_to(R)):sha(p) for p in files}),indent=2))
print('RETRY_SEALED; algorithm payloads identical; offline acceptance passed')
