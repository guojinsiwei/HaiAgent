"""Assemble isolated runtime; no credentials, model calls, or old source edits."""
import hashlib,json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
stage=ROOT/'runtime';runtime=stage/'kz-standalone';legacy=runtime/'legacy';legacy.mkdir(parents=True,exist_ok=True)
with tarfile.open(ROOT/'legacy-source.tar.gz') as t:t.extractall(legacy,filter='data')
for name in ('solve.py','anthropic_bridge.py','standalone-run.mjs','fixture.py'):shutil.copy2(ROOT/name,runtime/name)
with tarfile.open(ROOT/'legacy-runtime.tar.gz','w:gz') as t:t.add(runtime,arcname='kz-standalone')
provenance={str(p.relative_to(legacy)):hashlib.sha256(p.read_bytes()).hexdigest() for p in legacy.rglob('*.py')}
(ROOT/'legacy-provenance.json').write_text(json.dumps(provenance,indent=2))
print(json.dumps({'runtime_packaged':True,'python_sources':len(provenance),'api_calls':0}))
