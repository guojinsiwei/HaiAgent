"""Fresh campaign links to immutable public templates or independent grader inputs."""
import argparse
import json
from pathlib import Path
import shutil
from common import ROOT,save,sha

def main(side):
    if (ROOT/'ready.json').exists() or (ROOT/'college-ready.json').exists():
        raise RuntimeError('Already sealed; no preparation mutation allowed')
    if side=='solver':
        previous=Path('/mnt/lizh639/longcli-prediction-toggle10-20261003')
        for name in ('public','templates'):
            target=ROOT/name
            source=(previous/name).resolve(strict=True)
            if not target.exists():target.symlink_to(source,target_is_directory=True)
            assert target.resolve()==source
        # Exported templates are consumed read-only by make_root; every test/run
        # receives a fresh owned copy. No prior solved /app is ever used.
        for family in ('c-env','make-pytest'):
            source=ROOT/'templates'/family
            assert (source/'usr/bin/python3').is_file() and not (source/'tests').exists()
        save(ROOT/'reused-inputs.json',dict(public=str((ROOT/'public').resolve()),
            templates=str((ROOT/'templates').resolve()),prior_result_artifacts_used=False))
    else:
        previous=Path('/var/tmp/lizh639-longcli-prediction-toggle10-20261003')
        for name in ('upstream',):
            source=(previous/name).resolve(strict=True)
            target=ROOT/name
            if not target.exists():target.symlink_to(source,target_is_directory=True)
            assert target.resolve()==source
        shutil.copy2(previous/'input-manifest.json',ROOT/'input-manifest.json')
    print(json.dumps(dict(prepared=side,model_calls=0)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('side',choices=('solver','college'));main(p.parse_args().side)
