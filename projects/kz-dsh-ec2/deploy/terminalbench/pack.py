"""Build a source-only archive without credentials, dependencies or old runs."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
def main():
    names=[]
    for folder in ('src','scripts','tests'):
        names.extend(p for p in (PROJECT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    names.extend(PROJECT/n for n in ('package.json','package-lock.json'))
    with tarfile.open(ROOT/'source.tar.gz','w:gz') as archive:
        for p in sorted(names):archive.add(p,arcname=p.relative_to(PROJECT),recursive=False)
    files=[p for p in ROOT.iterdir() if p.suffix in ('.py','.mjs')]+[ROOT/'source.tar.gz']
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (ROOT/'source-lock.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as archive:
        for p in files+[ROOT/'source-lock.json']:archive.add(p,arcname=p.name,recursive=False)
    print(json.dumps(dict(files=len(names),sha256=hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest(),paid_calls=0)))
if __name__=='__main__':main()
