import json,re
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent
rows={}
for task in json.loads((ROOT/'tasks.json').read_text())['tasks']:
    for scope in ('environment','tests'):
        folder=ROOT/'official/tasks'/task['name']/scope
        for p in folder.rglob('*'):
            if not p.is_file():continue
            refs=[]
            if p.name.startswith('Dockerfile'):
                aliases=set()
                for line in p.read_text().splitlines():
                    m=re.fullmatch(r'FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?\s*(?:#.*)?',line,re.I)
                    if m:
                        ref,alias=m.groups()
                        if ref not in aliases and ref!='scratch' and '$' not in ref:refs.append(ref)
                        if alias:aliases.add(alias)
            elif p.name in ('docker-compose.yaml','docker-compose.yml'):
                doc=yaml.safe_load(p.read_text())
                refs=[s['image'] for s in doc.get('services',{}).values() if s.get('image') and '${' not in s['image']]
            for ref in refs:rows.setdefault(ref,[]).append(str(p.relative_to(ROOT)))
(ROOT/'base-images.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(list(rows),indent=2))
