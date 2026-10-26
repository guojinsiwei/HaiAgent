import hashlib,json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;S=R.parent/'tb2-three-arm50-boost6-20261018'
assert not (R/'prepared.json').exists()
for p in S.glob('*.py'):
 if not (R/p.name).exists():shutil.copy2(p,R/p.name)
for name in ['tasks.json','budget-profile.json','verifier-deps-provenance.json','history.json']:
 shutil.copy2(S/name,R/name)
for name in ['runtime-final.tar.gz','native-runtime.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz']:
 os.link(S/name,R/name)
(R/'venv').symlink_to(S/'venv',target_is_directory=True)
(R/'dependencies').mkdir();(R/'dependencies/official').symlink_to(S/'dependencies/official',target_is_directory=True)
shutil.copy2(S/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
shutil.copytree(S/'environment-locks',R/'environment-locks')
rows=json.loads((S/'health.json').read_text())['rows'];assert len(rows)==22
(R/'repair-plan.json').write_text(json.dumps(rows,indent=2))
(R/'prepared.json').write_text(json.dumps({'source':str(S),'changes':'verifier infrastructure only','paid_retries':21,'score_only':1}))
print('PREPARED')
