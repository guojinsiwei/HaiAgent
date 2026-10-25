"""Independent Recuris deployment; reuse ONLY immutable public inputs/grader."""
from pathlib import Path
import shutil
import json
from common import ROOT,sha,save
BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
DSH=Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')

def main():
    assert ROOT.name=='longcli-recuris-frozen-small20-20261007'
    for name in ('upstream','input-manifest.json'):
        p=ROOT/name
        if not p.exists():p.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    p=ROOT/'college_grader.py'
    if not p.exists():shutil.copyfile(DSH/'college_grader.py',p)
    assert sha(p)=='e557933f3896136ec32b0827e255b7f1b96027c56ec336de4403018425acd298'
    manifest=json.loads((ROOT/'recuris/HANDOFF_MANIFEST.json').read_text())
    for r in manifest['files']:
        p=ROOT/r['path']
        assert p.resolve().is_relative_to((ROOT/'recuris').resolve())
        assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
    for name in ('empty-tests','incoming','jobs','grades','host-tmp'):(ROOT/name).mkdir(exist_ok=True)
    save(ROOT/'remote-setup.json',{'paid_model_calls':0,'grader_sha256':sha(ROOT/'college_grader.py'),
                                 'handoff_files_verified':len(manifest['files'])})
if __name__=='__main__':main()
