"""Create an isolated engineering retry release; never edit the active campaign."""
import hashlib,json,shutil,subprocess
from pathlib import Path
P=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace(p,old,new):
 text=p.read_text();assert text.count(old)==1,(str(p),old[:50]);p.write_text(text.replace(old,new))
assert not (R/'prepared.json').exists(),'Refuse rebuilding an existing release'
for name in ['campaign.py','experiment.py','agents.py','host_agent.py','entry_harbor.py','lifecycle_guard.py','verifier_setup.py','connection_probe.py','native_results.py','queue_policy.py','recovery.py','receipts.py','storage.py','trial_runner.py','spending.py','tasks.json','budget-profile.json','verifier-deps-provenance.json','provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','protocol-fixtures.mjs','test-provider-guard.mjs','test_bounded_transport.mjs','test_bounded_ledger.py']:
 shutil.copy2(P/name,R/name)
for name in ['venv','python-runtime.tar.gz','native-runtime.tar.gz','verifier-deps.tar.gz']:(R/name).symlink_to(P/name)
(R/'dependencies').mkdir()
(R/'dependencies/official').symlink_to(P/'dependencies/official',target_is_directory=True)
shutil.copy2(P/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
# Only transport adapter changes in the packaged DSH runtime; algorithm archives
# and native runtime remain byte-identical. Never edit the source parent's tar.
replace(R/'provider-guard.mjs',"      await settle(lease,usage);\n      if(totalUsage(usage)===null)","""      if(response.ok && sse && totalUsage(usage)===null && attempt===0 && uncertainTransportResponses===0) {
        uncertainTransportResponses++;
        record({event:'settlement_attempt',lease,tokens:null,usage_known:false});
        try{await budget.settle(lease,null);}catch(e){if(e.message!=='usage_unavailable')stopBudget(e);}
        record({event:'uncertain_stream_retained',lease,recovery_allowed:true});
        retryAt=clock()+5000;continue;
      }
      await settle(lease,usage);
      if(totalUsage(usage)===null)""")
replace(R/'test-provider-guard.mjs',"unknown usage stops after one request without freeing its maximum","unknown SSE usage retains both maximums and stops after one recovery")
replace(R/'test-provider-guard.mjs',"assert.equal(calls,1);assert.equal(s.settlements[0].usage,null);","assert.equal(calls,2);assert.equal(s.settlements[0].usage,null);assert.equal(s.settlements[1].usage,null);")
replace(R/'verifier_setup.py',"UV_HTTP_TIMEOUT='90',UV_INDEX_URL='https://mirrors.ustc.edu.cn/pypi/simple',PIP_INDEX_URL='https://mirrors.ustc.edu.cn/pypi/simple'","UV_HTTP_TIMEOUT='120',UV_HTTP_RETRIES='3',UV_CONCURRENT_DOWNLOADS='2',UV_INDEX_URL='https://pypi.org/simple',PIP_INDEX_URL='https://pypi.org/simple',PIP_RETRIES='3'")
# Only environment preparation gets a larger deadline; solver and verifier
# deadlines and the official task files stay unchanged.
replace(R/'entry_harbor.py',"    Trial._compute_agent_timeout_sec=timeout","""    Trial._compute_agent_timeout_sec=timeout
    original_start=Trial._start_agent_environment
    async def retry_start(self):
        self._environment_build_timeout_sec=max(1800.0,self._environment_build_timeout_sec)
        return await original_start(self)
    Trial._start_agent_environment=retry_start""")
(R/'history.json').write_text('{}')
# Stream-repack the original archive without extracting untrusted task output.
import tarfile,io
changed=[]
with tarfile.open(P/'runtime-final.tar.gz','r:gz') as src,tarfile.open(R/'runtime-final.tar.gz','w:gz') as dst:
 for item in src:
  if item.name=='kz/provider-guard.mjs':
   data=(R/'provider-guard.mjs').read_bytes();item.size=len(data);dst.addfile(item,io.BytesIO(data));changed.append(item.name)
  else:dst.addfile(item,src.extractfile(item) if item.isfile() else None)
assert changed==['kz/provider-guard.mjs']
(R/'prepared.json').write_text(json.dumps(dict(parent=str(P),changed_archive_members=changed,parent_runtime_sha256=sha(P/'runtime-final.tar.gz'),retry_runtime_sha256=sha(R/'runtime-final.tar.gz'),native_sha256=sha(R/'native-runtime.tar.gz')),indent=2))
print('ISOLATED_RELEASE_PREPARED')
