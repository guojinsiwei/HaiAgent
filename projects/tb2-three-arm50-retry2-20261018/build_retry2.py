import hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parent
S=R.parent/'tb2-three-arm50-retry-20261018'
P=R.parent/'tb2-three-arm50-20261017'
assert not (R/'prepared.json').exists(),'Refuse overwriting prepared release'
def replace(p,old,new):
 text=p.read_text();assert text.count(old)==1,(p.name,old[:60]);p.write_text(text.replace(old,new))
names=['campaign.py','experiment.py','agents.py','host_agent.py','entry_harbor.py','lifecycle_guard.py','verifier_setup.py','connection_probe.py','native_results.py','queue_policy.py','recovery.py','receipts.py','storage.py','trial_runner.py','spending.py','tasks.json','budget-profile.json','verifier-deps-provenance.json','provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','protocol-fixtures.mjs','test-provider-guard.mjs','test_bounded_transport.mjs','test_bounded_ledger.py','test_retry.py','test_retry_stream.mjs','retry.py','seal_retry.py']
for name in names:shutil.copy2(S/name,R/name)
archives=['runtime-final.tar.gz','python-runtime.tar.gz','native-runtime.tar.gz','verifier-deps.tar.gz']
digests={}
for name in archives:
 shutil.copy2((S/name).resolve(strict=True),R/name);(R/name).chmod(0o644)
 assert not (R/name).is_symlink()
 digests[name]=hashlib.sha256((R/name).read_bytes()).hexdigest()
(R/'venv').symlink_to(P/'venv',target_is_directory=True)
(R/'dependencies').mkdir();(R/'dependencies/official').symlink_to(P/'dependencies/official',target_is_directory=True)
shutil.copy2(S/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
shutil.copytree(P/'environment-locks',R/'environment-locks')
(R/'history.json').write_text('{}')
for name in ('host_agent.py','agents.py','verifier_setup.py'):
 p=R/name;p.write_text('from upload_verified import upload_verified\n'+p.read_text())
 text=p.read_text()
 import re
 text,n=re.subn(r'await env.upload_file\((ROOT/[^,]+),([^\n]+)\)',r'await upload_verified(env,\1,\2)',text)
 assert n==({'host_agent.py':1,'agents.py':2,'verifier_setup.py':1}[name]),(name,n)
 p.write_text(text)
replace(R/'retry.py',"TERMINAL={'done','engineering_failure','historical'}","S=R.parent/'tb2-three-arm50-retry-20261018'\nTERMINAL={'done','engineering_failure','historical'}")
replace(R/'retry.py'," assert seal.get('tests_passed') is True,'Offline checks required'"," assert seal.get('tests_passed') is True,'Offline checks required'\n acceptance=read(R/'acceptance-real.json')\n assert acceptance.get('passed') is True and len(acceptance.get('results',[]))==3,'Real Docker acceptance required'\n for name in ('runtime-final.tar.gz','python-runtime.tar.gz','native-runtime.tar.gz','verifier-deps.tar.gz'):assert not (R/name).is_symlink(),'Archive symlink forbidden'")
replace(R/'retry.py',"job='retry1-'+old['job']","job='retry2-'+old['job']")
replace(R/'retry.py',"self.url='http://10.123.0.1:28716'","self.url='http://10.123.0.1:28726'")
replace(R/'retry.py',"self.token,'10.123.0.1',28716","self.token,'10.123.0.1',28726")
replace(R/'retry.py'," rows,skipped=select_rows(parent)\n atomic_json", " rows,skipped=select_remaining(parent)\n atomic_json")
replace(R/'retry.py',"campaign.PORT=28715","campaign.PORT=28725")
insert="""def select_remaining(parent):
 previous=read(S/'health.json')
 assert previous.get('state')=='finished' and not previous.get('active') and not owned_alive(previous.get('supervisor_identity')),'Previous retry must be quiescent'
 rows,skipped=select_rows(parent)
 prior={r['budget_job']:r for r in previous['rows']}
 eligible=[]
 for row in rows:
  old=prior.get(row['budget_job'])
  if old is None or old['state']!='engineering_failure':
   skipped.append(dict(job=row['budget_job'],reason='previous_retry_already_clean_or_not_selected'));continue
  offline=old.get('result',{}).get('reason')=='preflight_failed'
  if completed_attempt(S,old,offline) is None:
   skipped.append(dict(job=row['budget_job'],reason='previous_retry_ownership_not_confirmed'));continue
  row['previous_retry_result']=old.get('result',{});eligible.append(row)
 return eligible,skipped

"""
replace(R/'retry.py','def schedule(state,**extra):',insert+'def schedule(state,**extra):')
# Add real acceptance and upload regression checks to the frozen release gate.
replace(R/'seal_retry.py',"'test_retry','test_bounded_ledger'","'test_retry','test_bounded_ledger','test_upload_verified'")
replace(R/'seal_retry.py',"files=[p for p in R.iterdir()", "acceptance=json.loads((R/'acceptance-real.json').read_text());assert acceptance['passed'] and len(acceptance['results'])==3\nprotocol['scope']='One retry of remaining engineering failures after retry1; exclude its clean score zero'\nprotocol['changes'].append('Physical readable archives with host/container SHA-256 checks; three real keyless Docker acceptance trials required')\n(R/'protocol.json').write_text(json.dumps(protocol,indent=2))\nfiles=[p for p in R.iterdir()")
(R/'prepared.json').write_text(json.dumps(dict(previous=str(S),archives=digests,physical_archives=True),indent=2))
print('RETRY2_PREPARED')
