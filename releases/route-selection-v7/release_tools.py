"""Build hash manifest for this isolated repair; never modify frozen sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sources = ROOT / 'sources'
hashes = {str(p.relative_to(sources)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(sources.rglob('*.py'))}
baseline = json.loads((ROOT / 'baseline-manifest.json').read_text())
changes = [dict(path=row['path'], before=row['sha256'], after=hashes[row['path']])
           for row in baseline if hashes[row['path']] != row['sha256']]
known = {row['path'] for row in baseline}
changes += [dict(path=name, before=None, after=value) for name, value in hashes.items()
            if name not in known and '/src/' in name]
(ROOT / 'fixed-source-manifest.json').write_text(json.dumps(hashes, indent=2))
(ROOT / 'changed-sources.json').write_text(json.dumps(changes, indent=2))
(ROOT / 'integration-source-manifest.json').write_text(json.dumps({
    str(p.relative_to(ROOT / 'integration')): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((ROOT / 'integration').glob('*.py'))}, indent=2))
print(json.dumps(dict(source_files=len(hashes), changed=changes), indent=2))
