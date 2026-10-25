"""Reuse immutable public starters and grader only; no credentials or old states."""
from pathlib import Path
import shutil
from common import ROOT,sha,save

BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
DSH=Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')

def main():
    assert ROOT.name=='longcli-lats-taco-small20-20261007'
    for name in ('upstream','input-manifest.json'):
        target=ROOT/name
        if not target.exists():target.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    target=ROOT/'college_grader.py'
    if not target.exists():shutil.copyfile(DSH/'college_grader.py',target)
    assert sha(target)=='e557933f3896136ec32b0827e255b7f1b96027c56ec336de4403018425acd298'
    for name in ('empty-tests','incoming','jobs','grades','host-tmp'):(ROOT/name).mkdir(exist_ok=True)
    save(ROOT/'remote-setup.json',{'paid_model_calls':0,'grader_sha256':sha(target)})

if __name__=='__main__':main()
