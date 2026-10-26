"""Seal an isolated repair against the original frozen v6, cross-platform."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT.parent/'monitor-control-v6'

def hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*.py'))}

def save(name, value):
    (ROOT/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

baseline = hashes(ORIGINAL/'sources')
current = hashes(ROOT/'sources')
save('baseline-manifest.json', [dict(path=p, sha256=h, origin='/var/tmp/lizh639-monitor-control-v6/sources/'+p)
                                for p, h in baseline.items()])
save('fixed-source-manifest.json', current)
save('integration-source-manifest.json', hashes(ROOT/'integration'))
save('changed-sources.json', [dict(path=p, before=baseline.get(p), after=h)
                             for p, h in current.items() if baseline.get(p) != h])
save('repair-manifest.json', dict(version='v6.1', baseline='monitor-control-v6',
     original_sources=baseline, source_changes=[p for p in current if current[p] != baseline.get(p)],
     integration_changes=[p for p, h in hashes(ROOT/'integration').items()
                          if h != hashes(ORIGINAL/'integration').get(p)],
     test_files=hashes(ROOT/'tests'), model_calls=0))
print(json.dumps(dict(source_files=len(current), changed=[p for p in current if current[p] != baseline.get(p)])))
