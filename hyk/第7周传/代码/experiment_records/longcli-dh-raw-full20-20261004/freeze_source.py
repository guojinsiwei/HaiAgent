"""Pin DH provenance and assert only the previously tested prediction switch was merged."""
import json
from pathlib import Path
from common import ROOT,sha,save

def main():
    base=ROOT.parent.parent/'releases/recovery-counter-fix-v9/sources/bestfgs-project/src/bestfgs'
    current=ROOT/'sources/bestfgs-project/src/bestfgs'
    changed=[]
    hashes={}
    for path in current.rglob('*.py'):
        if '__pycache__' in path.parts:continue
        name=path.relative_to(current).as_posix();hashes[name]=sha(path)
        assert (base/name).is_file(),name
        if hashes[name]!=sha(base/name):changed.append(name)
    assert sorted(changed)==['contrastive_exploration.py','lean_protocol.py'],changed
    save(ROOT/'dh-source-manifest.json',dict(name='DH',base='recovery-counter-fix-v9',
        merged_existing_switch_from='longcli-prediction-toggle10-20261003',changed_files=sorted(changed),
        contrastive_predictions=False,route_search=False,hashes=hashes))
    print(json.dumps(dict(name='DH',source_files=len(hashes),changed_from_counter_fix=changed)))

if __name__=='__main__':main()
