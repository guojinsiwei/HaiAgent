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
from audit import verify
from device_setup import prepare_devices

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
    prepare_devices(root)
    return root

def make_fixture_root(row, worker, cache):
    """Reuse a toolchain only offline; replace the complete public app each time.

    Paid trials always call make_root and receive independent full roots.
    Old fixture apps are retained, not merged into the next task.
    """
    family=row['family']
    if family not in cache:
        # A previously completed fixture is an owned, verified clean toolchain.
        old_job='worker'+str(worker)+'-v2-'+('dh' if worker==0 else 'raw')+'--cs61_fa24_scheme'
        previous=ROOT/'roots'/old_job
        report=ROOT/'fixtures'/old_job/'summary.json'
        if family=='make-pytest' and report.exists():
            old=json.loads(report.read_text())
            assert old['fixture'] and old['submitted'] and old['tool_calls']==1
            cache[family]=previous
        else:
            cache[family]=make_root(row,name='offline-worker'+str(worker)+'-'+family)
    root=cache[family]
    retired=ROOT/'offline-retired'/row['job'];retired.parent.mkdir(exist_ok=True)
    (root/'app').rename(retired)
    app=root/'app';app.mkdir()
    for source in (ROOT/'public'/row['task']).iterdir():
        target=app/source.name
        if source.is_dir():shutil.copytree(source,target,symlinks=True)
        else:shutil.copy2(source,target)
    own(app);prepare_devices(root)
    return root

def main(worker,resume=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    assert not (ROOT/('health-'+str(worker)+'.json')).exists(),'Already launched'
    for family in protocol['base_images']:
        target=ROOT/'templates'/family
        assert (target/'usr/bin/python3').is_file() and not (target/'tests').exists()
    checks=[]
    fixture_cache={}
    prior=set()
    if resume:
        assert not (ROOT/'claims').exists(),'Never resume preparation after paid claims'
        old_log=ROOT/f'solver-preflight-{worker}.log'
        for line in old_log.read_text().splitlines():
            try:item=json.loads(line)
            except ValueError:continue
            if item.get('model_calls')==0 and item.get('checked'):prior.add(item['checked'])
    for row in assignments(protocol,worker):
        # Fixture roots are separate from all paid-trial roots.
        row=dict(row,job='worker'+str(worker)+'-v4-'+row['job'])
        if row['job'] in prior:
            base=ROOT/'fixtures'/row['job'];summary=json.loads((base/'summary.json').read_text())
            assert summary['fixture'] and summary['submitted'] and summary['tool_calls']==1
            assert summary['method']==row['method'] and summary['task']==row['task']
            assert verify(base/'model-audit.jsonl')==summary['audit']
            assert sha(base/'source.tar.gz')==summary['artifact']['sha256']
            checks.append(dict(task=row['task'],method=row['method'],isolation_previously_asserted=True,
                checkpoint_restore=True,masked_pipeline_failure=True,submitted=True,model_calls=0,
                provenance='Retained completed fixture plus trusted original assert-before-checked log',
                fixture_job=row['job'],original_log_sha256=sha(old_log)))
            continue
        if resume:
            row=dict(row,job=row['job'].replace('-v2-','-v3-',1))
        root=make_fixture_root(row,worker,fixture_cache)
        row['fixture_root']=str(root)
        env=NativeEnvironment(root,ROOT/'preflight-checkpoints'/row['job'])
        isolated=json.loads(env.probe('import os,json,socket; from pathlib import Path; '
            's=socket.socket(); network=False; '
            '\ntry: s.connect(("1.1.1.1",443)); network=True\nexcept OSError: pass\n'
            'print(json.dumps(dict(uid=os.getuid(),no_proc=not Path("/proc/1/environ").exists(),'
            'no_host=not Path("/mnt/lizh639").exists(),no_tests=not Path("/tests").exists(),no_network=not network)))'))
        assert isolated['uid']==0 and all(isolated[k] for k in ('no_proc','no_host','no_tests','no_network'))
        clean=env.execute(dict(argv=['bash','-lc',
            'python3 -c "import os; f=os.open(\'/dev/null\',os.O_RDWR); '
            'assert os.write(f,b\'probe\')==5; assert os.read(f,1)==b\'\'; '
            'os.close(f); print(\'device-ok\')"'],timeout_seconds=30),time.monotonic()+30)
        assert clean.return_code==0 and clean.stdout.strip()=='device-ok' and not clean.stderr,clean
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
        if row['task'].startswith('61810_'):
            # Compile a disposable RISC-V program and boot a tiny independent
            # firmware. No hidden tests or task solution are used.
            script = ('import subprocess; from pathlib import Path; '
                'p=Path("/tmp/probe.S"); p.write_text(".section .text\\n.globl _start\\n_start:\\n li t0,0x10000000\\n li t1,81\\n sb t1,0(t0)\\n1: j 1b\\n"); '
                'subprocess.run(["riscv64-linux-gnu-gcc","-nostdlib","-march=rv64g","-mabi=lp64d",'
                '"-Wl,-Ttext=0x80000000",str(p),"-o","/tmp/probe.elf"],check=True); '
                '\ntry: subprocess.run(["qemu-system-riscv64","-machine","virt","-bios","none",'
                '"-kernel","/tmp/probe.elf","-nographic","-monitor","none","-serial","stdio"],'
                'capture_output=True,timeout=3,check=True)\n'
                'except subprocess.TimeoutExpired as e: assert b"Q" in (e.stdout or b""),repr(e.stdout)\n'
                'print("riscv-qemu-ok")')
            assert env.probe(script).endswith('riscv-qemu-ok')
        # Frozen source selection requires a fresh interpreter per method.
        runner_env=dict(os.environ,LONGCLI_METHOD=row['method'])
        spec=ROOT/'fixtures'/(row['job']+'-spec.json');save(spec,row)
        completed=subprocess.run([str(Path('/mnt/lizh639/envs/swe-eval/bin/python')),'-B',str(ROOT/'fixture_runner.py'),str(spec)],
            env=runner_env,capture_output=True,text=True,check=True,timeout=180)
        summary=json.loads(completed.stdout.strip().splitlines()[-1])
        assert summary['submitted'] and summary['tool_calls']==1
        checks.append(dict(task=row['task'],method=row['method'],isolation=isolated,checkpoint_restore=True,
                           masked_pipeline_failure=True,riscv_qemu=row['task'].startswith('61810_'),
                           fresh_public_app=True,fixture_root_reused_offline_only=True,submitted=True,model_calls=0))
        print(json.dumps(dict(checked=row['job'],model_calls=0)),flush=True)
    save(ROOT/('preflight-'+str(worker)+'.json'),dict(passed=True,worker=worker,checks=checks,model_calls=0))
    print(json.dumps(dict(worker=worker,preflight_passed=True,model_calls=0)),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=int,choices=(0,1),required=True)
    parser.add_argument('--resume-offline',action='store_true')
    args=parser.parse_args();main(args.worker,args.resume_offline)
