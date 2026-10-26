"""Build campaign-local immutable runtime; no credentials or paid API calls."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=Path('/var/tmp/lizh639-longcli-kz-dsh3-repair5-20261013/runtime')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    runtime=ROOT/'runtime'
    if (ROOT/'runtime.tar.gz').exists():raise SystemExit('Runtime sealed; refuse overwrite')
    runtime.mkdir(exist_ok=True)
    for src,dest in [(OLD/'node',runtime/'node'),(OLD/'kz/node_modules',runtime/'kz/node_modules')]:
        if not dest.exists():shutil.copytree(src,dest,symlinks=True)
    kz=runtime/'kz'
    with tarfile.open(ROOT/'candidate.tar.gz') as f:f.extractall(kz,filter='data')
    manifest=json.loads((ROOT/'source-manifest.json').read_text())
    for n,h in manifest['files'].items():assert sha(kz/n)==h,n
    for n in ('shared-budget.mjs','route.patch.yml','container-run.mjs','boot-guard.mjs'):
        shutil.copy2(ROOT/n,kz/n)
    shutil.copy2(OLD/'kz/route-audit.mjs',kz/'route-audit.mjs')
    subprocess.run([str(runtime/'node/bin/node'),str(kz/'scripts/prepare-config.mjs'),'--plugin-path','/opt/kz/src/plugin.mjs'],check=True)
    p=kz/'.runtime/kz.patch.yml';s=p.read_text();assert s.count('shellReceipts: false')==1
    p.write_text(s.replace('shellReceipts: false','shellReceipts: true'))
    subprocess.run(['tar','-czf',str(ROOT/'runtime.tar.gz'),'-C',str(runtime),'node','kz'],check=True)
    (ROOT/'runtime-manifest.json').write_text(json.dumps(dict(version='0.2.7',archive_sha256=sha(ROOT/'runtime.tar.gz'),files={str(p.relative_to(kz)):sha(p) for p in kz.rglob('*') if p.is_file() and 'node_modules' not in p.parts}),indent=2))
    print(json.dumps(dict(runtime_sha256=sha(ROOT/'runtime.tar.gz'),paid_calls=0)))
if __name__=='__main__':main()
