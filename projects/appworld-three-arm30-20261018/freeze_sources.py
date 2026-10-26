from pathlib import Path
import hashlib,json,shutil,tarfile
R=Path(__file__).resolve().parent
roots={'hld':R.parent/'HLD','kzdsh-new':R.parent/'kz-dsh-exploration-v2-20261018/candidate','recuris-dsh':R.parent/'recuris-dsh','dsh-baselines':R.parent/'dsh-baselines'}
manifest={}
# Use a fresh snapshot directory so removed files cannot survive a re-freeze.
import time
snapshot=R/('sources-'+str(time.time_ns()));snapshot.mkdir()
for name,source in roots.items():
    dest=snapshot/name
    for part in ['src','tests','config','scripts','vendor','worker.py','package.json','README.txt']:
        src=source/part
        if not src.exists():continue
        if src.is_dir():
            shutil.copytree(src,dest/part,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','node_modules','upstream'))
        else:
            dest.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest/part)
    for p in dest.rglob('*'):
        if p.is_file():manifest['sources/'+str(p.relative_to(snapshot)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'source-lock.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(R/'sources.tar.gz','w:gz') as out:
    for name in roots:out.add(snapshot/name,arcname='sources/'+name)
    out.add(R/'source-lock.json',arcname='source-lock.json')
print('Frozen files',len(manifest))
