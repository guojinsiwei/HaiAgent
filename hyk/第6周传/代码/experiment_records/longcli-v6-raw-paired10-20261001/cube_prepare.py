"""Prepare public-only isolated roots and perform zero-API checks."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from common import ROOT, sha, save, assignments
from runner import run_one
from environment import NativeEnvironment

def own(path):
    for parent,dirs,files in os.walk(path,followlinks=False):
        os.chown(parent,65534,65534,follow_symlinks=False)
        for name in dirs+files:
            os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)

def make_root(row, name=None):
    root=ROOT/'roots'/(name or row['job'])
    root.mkdir(parents=True,exist_ok=False)
    subprocess.run(['cp','-a','--reflink=auto',str(ROOT/'templates'/row['family'])+'/.',str(root)],check=True,timeout=600)
    app=root/'app'
    app.mkdir(exist_ok=True)
    for source in (ROOT/'public'/row['task']).iterdir():
        target=app/source.name
        if source.is_dir(): shutil.copytree(source,target,symlinks=True)
        else: shutil.copy2(source,target)
    own(app)
    own(root/'tmp')
    return root

def main(worker):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    assert not (ROOT/('health-'+str(worker)+'.json')).exists(),'Already launched'
    if worker==0:
        for family,info in protocol['base_images'].items():
            archive=ROOT/info['archive']
            assert sha(archive)==info['sha256'],'Changed official rootfs'
            target=ROOT/'templates'/family
            marker=ROOT/('template-'+family+'.json')
            if not marker.exists():
                target.mkdir(parents=True,exist_ok=True)
                subprocess.run(['tar','-xf',str(archive),'-C',str(target),'--no-same-owner'],check=True,timeout=600)
                save(marker,dict(rootfs_sha256=info['sha256'],complete=True))
            assert json.loads(marker.read_text())['rootfs_sha256']==info['sha256']
            assert not (target/'tests').exists()
    checks=[]
    for row in assignments(protocol,worker):
        # Fixture roots are separate from all paid-trial roots.
        row=dict(row,job='worker'+str(worker)+'-v2-'+row['job'])
        root=make_root(row)
        env=NativeEnvironment(root,ROOT/'preflight-checkpoints'/row['job'])
        isolated=json.loads(env.probe('import os,json,socket; from pathlib import Path; '
            's=socket.socket(); network=False; '
            '\ntry: s.connect(("1.1.1.1",443)); network=True\nexcept OSError: pass\n'
            'print(json.dumps(dict(uid=os.getuid(),no_proc=not Path("/proc/1/environ").exists(),'
            'no_host=not Path("/mnt/lizh639").exists(),no_tests=not Path("/tests").exists(),no_network=not network)))'))
        assert isolated['uid']==0 and all(isolated[k] for k in ('no_proc','no_host','no_tests','no_network'))
        checkpoint=env.checkpoint('fixture-baseline')
        env.execute(dict(argv=['python3','-c','from pathlib import Path; Path("fixture.txt").write_text("x")']),time.monotonic()+30)
        env.restore(checkpoint)
        assert not (root/'app/fixture.txt').exists()
        env.outcome_reliability=True
        outcome=env.execute(dict(argv=['bash','-lc','false | true']),time.monotonic()+30)
        assert outcome.return_code==0 and outcome.execution_observation['nonzero_statuses'],outcome
        if row['family']=='c-env':
            # Compilation probe in /tmp, no solution or hidden test input.
            assert 'cpp-ok' in env.probe('import subprocess; from pathlib import Path; '
                'p=Path("/tmp/probe.cc"); p.write_text("int main(){return 0;}"); '
                'subprocess.run(["g++",str(p),"-o","/tmp/probe"],check=True); '
                'subprocess.run(["/tmp/probe"],check=True); print("cpp-ok")')
        summary=run_one(row,fixture=True)
        assert summary['submitted'] and summary['tool_calls']==1
        checks.append(dict(task=row['task'],method=row['method'],isolation=isolated,checkpoint_restore=True,
                           masked_pipeline_failure=True,submitted=True,model_calls=0))
        print(json.dumps(dict(checked=row['job'],model_calls=0)),flush=True)
    save(ROOT/('preflight-'+str(worker)+'.json'),dict(passed=True,worker=worker,checks=checks,model_calls=0))
    print(json.dumps(dict(worker=worker,preflight_passed=True,model_calls=0)),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=int,choices=(0,1),required=True)
    main(parser.parse_args().worker)
