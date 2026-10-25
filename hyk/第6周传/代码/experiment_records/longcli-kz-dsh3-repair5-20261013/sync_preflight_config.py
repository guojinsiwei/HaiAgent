"""Apply only an explicitly enumerated pre-launch config fix, preserving evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from common import ROOT,sha,save
assert not (ROOT/'ready.json').exists() and not (ROOT/'launch-once.marker').exists() and not (ROOT/'jobs').exists()
kz=ROOT/'runtime/kz';backup=ROOT/'preflight-config-original';backup.mkdir()
old=json.loads((ROOT/'manifest.json').read_text());new=json.loads((ROOT/'source-manifest.json').read_text())
changes=[n for n,h in new['files'].items() if not (kz/n).exists() or sha(kz/n)!=h]
assert set(changes)=={'scripts/prepare-config.mjs','README.txt','tests/deployment-config.test.mjs'},changes
for name in changes:
    if (kz/name).exists():
        target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(kz/name,target)
with tarfile.open(ROOT/'candidate.tar.gz') as archive:
    for name in changes:archive.extract(name,kz,filter='data')
obsolete=kz/'config/longcli-task.patch.yml'
assert obsolete.is_file() and obsolete.resolve().is_relative_to(ROOT)
obsolete.rename(backup/'retired-longcli-task.patch.yml')
shutil.copy2(ROOT/'manifest.json',backup/'manifest.json')
shutil.copy2(kz/'.runtime/kz.patch.yml',backup/'materialized-kz.patch.yml')
shutil.copy2(ROOT/'kz-boot-guard.mjs',kz/'kz-boot-guard.mjs')
subprocess.run([str(ROOT/'runtime/node/bin/node'),str(kz/'scripts/prepare-config.mjs'),'--longcli','--plugin-path','/opt/kz/src/plugin.mjs'],check=True)
for name,expected in new['files'].items():assert sha(kz/name)==expected,name
for name in ('regressions.tap','regressions.stderr','offline-native.log'):
    if (ROOT/name).exists():shutil.copy2(ROOT/name,backup/name)
(ROOT/'offline-native').rename(backup/'offline-native')
old['files'].pop('runtime/kz/config/longcli-task.patch.yml')
for name,expected in new['files'].items():old['files']['runtime/kz/'+name]=expected
for name in ('source-manifest.json','prepare.py','accept.py','container_run.py','offline.py','kz-boot-guard.mjs','sync_preflight_config.py','runtime/kz/kz-boot-guard.mjs','runtime/kz/.runtime/kz.patch.yml'):
    old['files'][name]=sha(ROOT/name)
save(ROOT/'manifest.json',old)
save(ROOT/'preflight-config-repair.json',dict(reason='DSH config blocks replace, not deep-merge; generate full config, fail closed before provider if KZ inactive',algorithm_source_changed=False,paid_api_calls=0,changed=changes))
print('Complete LongCLI config materialized; first failed native preflight preserved; no algorithm source changed.')
