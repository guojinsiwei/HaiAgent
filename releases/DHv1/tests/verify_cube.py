"""Zero-API acceptance in the actual CubeStudio namespace executor."""
import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OLD = Path('/mnt/lizh639/longcli-threeway-engineering-20261003')
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'harness'),
               str(ROOT/'compatibility/src')]
# Import the candidate package before the compatibility executor modifies sys.path.
import bestfgs.lean_runtime
from environment import NativeEnvironment, SandboxExecutor
from device_setup import prepare_devices


def own(path):
    for base, dirs, files in os.walk(path, followlinks=False):
        os.chown(base, 65534, 65534, follow_symlinks=False)
        for name in dirs+files:
            os.chown(Path(base)/name,65534,65534,follow_symlinks=False)


def main(reuse=False):
    results=[]
    for family in ('make-pytest','c-env'):
        root=ROOT/'fixture-roots'/family
        if not (reuse and root.exists()):
            root.mkdir(parents=True,exist_ok=False)
            subprocess.run(['cp','-a','--reflink=auto',str(OLD/'templates'/family)+'/.',str(root)],
                           check=True,timeout=600)
        (root/'app').mkdir(exist_ok=True)
        own(root/'app');own(root/'tmp')
        device=prepare_devices(root)
        worker=os.environ.get('V9_WORKER','unknown')
        env=NativeEnvironment(root,ROOT/'fixture-checkpoints'/('worker'+worker+'-'+family))
        action=dict(argv=['bash','-lc',
            'python3 -c "import os; f=os.open(\'/dev/null\',os.O_RDWR); '
            'assert os.write(f,b\'probe\')==5; assert os.read(f,1)==b\'\'; '
            'os.close(f); print(\'device-ok\')"'],cwd='.',timeout_seconds=30)
        outcome=env.execute(action,time.monotonic()+30)
        assert outcome.return_code==0 and outcome.stdout.strip()=='device-ok' and not outcome.stderr,outcome
        # Pipeline observation must still work after removing the startup noise.
        env.outcome_reliability=True
        piped=env.execute(dict(argv=['bash','-lc','false | true'],cwd='.'),time.monotonic()+30)
        assert piped.return_code==0 and not piped.stderr and piped.execution_observation['nonzero_statuses'],piped
        isolation=json.loads(env.probe('import os,json,socket; from pathlib import Path; '
            's=socket.socket(); network=False; '
            '\ntry:s.connect(("1.1.1.1",443));network=True\nexcept OSError:pass\n'
            'print(json.dumps(dict(uid=os.getuid(),no_proc=not Path("/proc/1/environ").exists(),'
            'no_host=not Path("/mnt/lizh639").exists(),no_tests=not Path("/tests").exists(),no_network=not network)))'))
        assert isolation['uid']==0 and all(isolation[k] for k in ('no_proc','no_host','no_tests','no_network'))
        checkpoint=env.checkpoint('before fixture edit')
        env.execute(dict(argv=['python3','-c',
            'from pathlib import Path; Path("fixture.txt").write_text("x")'],cwd='.'),time.monotonic()+30)
        env.restore(checkpoint)
        assert not (root/'app/fixture.txt').exists()
        if family=='c-env':
            cpp=env.execute(dict(argv=['bash','-lc',
                "printf 'int main(){return 0;}' >/tmp/probe.cc && g++ /tmp/probe.cc -o /tmp/probe && /tmp/probe"],
                cwd='.',timeout_seconds=60),time.monotonic()+60)
            assert cpp.return_code==0 and not cpp.stderr,cpp
        results.append(dict(family=family,device=device,clean_shell=True,
            pipeline_observation=True,isolation=isolation,checkpoint_restore=True,model_calls=0))
        print(json.dumps(results[-1]),flush=True)
    test=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'tests'),'-q'],
                        capture_output=True,text=True,timeout=120)
    assert test.returncode==0,test.stdout+test.stderr
    report=dict(passed=True,worker=os.environ.get('V9_WORKER','unknown'),checks=results,
                behavioral_tests=122,model_calls=0,updated=time.time())
    (ROOT/('cube-acceptance-'+worker+'.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-fixtures',action='store_true')
    main(parser.parse_args().reuse_fixtures)
