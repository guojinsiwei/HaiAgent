"""Package only owned code, protocol, source and offline fixtures; no credentials."""
from pathlib import Path
import hashlib
import json
import shutil
import tarfile
ROOT=Path(__file__).resolve().parent
RELEASE=ROOT.parents[1]/'releases/DH-routing-v1'
def main():
    for rel in ('sources/bestfgs-project/src/bestfgs/error_routing.py',
                'sources/bestfgs-project/src/bestfgs/lean_runtime.py','tests/test_error_routing.py'):
        shutil.copyfile(RELEASE/rel,ROOT/rel)
    hashes={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
            for top in ('sources','compatibility') for f in (ROOT/top).rglob('*.py')}
    (ROOT/'source-provenance.json').write_text(json.dumps({'base':'DH-subgoal-v1',
        'release':'DH-routing-v1','same_sources_for_all_arms':True,'hashes':hashes},indent=2))
    allowed={'.py','.json','.txt','.toml','.ps1','.md','.yaml','.yml'}
    added=[]
    with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as out:
        for f in ROOT.rglob('*'):
            if not f.is_file() or f.suffix not in allowed:continue
            rel=f.relative_to(ROOT)
            if any(part in {'.git','__pycache__','.pytest_cache','.venv','test-deps'} for part in rel.parts):continue
            if rel.parts[0] not in {'sources','compatibility','tests','evidence'} and len(rel.parts)>1:continue
            if any(token in f.name.lower() for token in ('.env','credential','private_key')):continue
            if rel.parts[0]=='evidence' and f.name!='previous-rejected-candidates.json':continue
            out.add(f,arcname=rel.as_posix());added.append(rel.as_posix())
    (ROOT/'deployment-manifest.json').write_text(json.dumps({'files':added,
        'sha256':hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest()},indent=2))
    print(json.dumps({'files':len(added),'bytes':(ROOT/'deployment.tar.gz').stat().st_size}))
if __name__=='__main__':main()
