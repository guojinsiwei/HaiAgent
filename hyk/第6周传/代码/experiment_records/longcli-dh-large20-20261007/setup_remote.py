"""Reuse only immutable pinned inputs. Never import another run's credentials."""
import json
from pathlib import Path
import shutil
from common import ROOT,sha,save

BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
DSH=Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')

def main():
    assert ROOT.name=='longcli-dh-large20-20261007' or ROOT.name=='lizh639-longcli-dh-large20-20261007'
    # Runtime ROOT.name must match the protocol/ownership labels across all components.
    for name in ('upstream','input-manifest.json'):
        (ROOT/name).symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    shutil.copyfile(DSH/'college_grader.py',ROOT/'college_grader.py')
    assert sha(ROOT/'college_grader.py')=='e557933f3896136ec32b0827e255b7f1b96027c56ec336de4403018425acd298'
    (ROOT/'empty-tests').mkdir()
    (ROOT/'incoming').mkdir();(ROOT/'jobs').mkdir();(ROOT/'grades').mkdir()
    save(ROOT/'remote-setup.json',{'model_calls':0,'grader_sha256':sha(ROOT/'college_grader.py')})

if __name__=='__main__':main()
