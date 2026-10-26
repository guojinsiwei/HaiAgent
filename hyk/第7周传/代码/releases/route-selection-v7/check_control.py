"""Read-only baseline/default checks. Writes evidence only in this new release."""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent


def defaults(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LeanConfig')
    return {n.target.id:ast.literal_eval(n.value) for n in cls.body if isinstance(n,ast.AnnAssign)}


def main(control):
    mismatches=[]
    totals={}
    for manifest_name,subdir in (('control-source-manifest.json','sources'),
                                 ('control-integration-manifest.json','integration')):
        expected=json.loads((ROOT/manifest_name).read_text())
        actual={str(p.relative_to(control/subdir)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (control/subdir).rglob('*.py')}
        mismatches += [subdir+'/'+name for name in set(expected)|set(actual) if expected.get(name)!=actual.get(name)]
        totals[subdir]=len(expected)
    relative='sources/bestfgs-project/src/bestfgs/lean_protocol.py'
    old,new=defaults(control/relative),defaults(ROOT/relative)
    shared_changed={k:dict(control=v,treatment=new.get(k)) for k,v in old.items() if new.get(k)!=v}
    hai=list((control/'sources/hai-project/src').rglob('*.py'))
    hai_changed=[str(p.relative_to(control)) for p in hai if
                 p.read_bytes()!=(ROOT/p.relative_to(control)).read_bytes()]
    result=dict(success=not mismatches and not shared_changed and not hai_changed,
        control_path=str(control),control_manifest_counts=totals,control_changes=mismatches,
        shared_lean_defaults_changed=shared_changed,new_lean_defaults={k:v for k,v in new.items() if k not in old},
        hai_source_count=len(hai),hai_changes=hai_changed,
        note='Checks source preservation and shared low-level defaults, not a sealed paid-run configuration.')
    (ROOT/'evidence').mkdir(exist_ok=True)
    (ROOT/'evidence/control-preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['success'] else 1


if __name__=='__main__':sys.exit(main(Path(sys.argv[1]).resolve()))
