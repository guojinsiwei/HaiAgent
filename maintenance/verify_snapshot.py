"""Verify the imported source snapshot without executing project code."""
from pathlib import Path
import hashlib,json,sys

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'maintenance/source-manifest.json').read_text(encoding='utf-8'))
errors=[]
for entry in manifest['files']:
    rel=Path(entry['path'])
    if rel.is_absolute() or '..' in rel.parts:
        errors.append(f'Unsafe path: {rel}');continue
    p=root/rel
    if not p.is_file():
        errors.append(f'Missing: {rel}');continue
    if hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
        errors.append(f'Hash mismatch: {rel}')
print(json.dumps({'checked':len(manifest['files']),'errors':errors},ensure_ascii=False))
sys.exit(bool(errors))
