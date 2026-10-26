import hashlib,json,os,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parent;S=R.parent/'tb2-three-arm50-retry2-20261018'
sys.path.insert(0,str(S));import retry;retry.validate()
assert not (R/'prepared.json').exists()
names=['campaign.py','experiment.py','agents.py','host_agent.py','entry_harbor.py','lifecycle_guard.py','verifier_setup.py','connection_probe.py','native_results.py','queue_policy.py','recovery.py','receipts.py','storage.py','trial_runner.py','spending.py','upload_verified.py','tasks.json','budget-profile.json','verifier-deps-provenance.json','history.json','acceptance-real.json']
for name in names:shutil.copy2(S/name,R/name)
for name in ['runtime-final.tar.gz','native-runtime.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz']:
 assert not (S/name).is_symlink();os.link(S/name,R/name)
(R/'venv').symlink_to(S/'venv',target_is_directory=True)
(R/'dependencies').mkdir();(R/'dependencies/official').symlink_to(S/'dependencies/official',target_is_directory=True)
shutil.copy2(S/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
shutil.copytree(S/'environment-locks',R/'environment-locks')
(R/'prepared.json').write_text(json.dumps(dict(source=str(S),runtime_unchanged=True)))
print('BOOST_PREPARED')
