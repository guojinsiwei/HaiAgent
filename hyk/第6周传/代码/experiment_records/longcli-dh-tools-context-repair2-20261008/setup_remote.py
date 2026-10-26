"""Use existing immutable task assets and official grader on the compute node."""
from pathlib import Path
import json
import shutil
from common import ROOT,save,sha
BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
DSH=Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')
def main():
    assert ROOT.name=='longcli-dh-tools-context-repair2-20261008'
    for name in ('upstream','input-manifest.json'):
        target=ROOT/name
        if not target.exists():target.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    shutil.copyfile(DSH/'college_grader.py',ROOT/'college_grader.py')
    assert sha(ROOT/'college_grader.py')=='e557933f3896136ec32b0827e255b7f1b96027c56ec336de4403018425acd298'
    for name in ('empty-tests','jobs','grades','incoming','acceptance-jobs','host-tmp','evidence'):
        (ROOT/name).mkdir(exist_ok=True)
    save(ROOT/'setup.json',{'paid_model_calls':0,'grader_sha256':sha(ROOT/'college_grader.py')})
    print('{"setup":true,"paid_model_calls":0}')
if __name__=='__main__':main()
