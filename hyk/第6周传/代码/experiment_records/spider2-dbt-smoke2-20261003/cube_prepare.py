"""Public-only native DBT root preparation and zero-API acceptance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from common import ROOT,PYTHON,save,sha,assignments
from device_setup import prepare_devices
from environment import NativeEnvironment


def own(path):
    for parent,dirs,files in os.walk(path,followlinks=False):
        os.chown(parent,65534,65534,follow_symlinks=False)
        for name in dirs+files:os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)


def make_root(row):
    root=ROOT/'roots'/row['job'];root.mkdir(parents=True,exist_ok=False)
    subprocess.run(['cp','-a','--reflink=auto',str(ROOT/'template')+'/.',str(root)],check=True,timeout=600)
    app=root/'app';app.mkdir(exist_ok=True)
    for source in (ROOT/'public'/row['task']).iterdir():
        target=app/source.name
        if source.is_dir():shutil.copytree(source,target,symlinks=True)
        else:shutil.copy2(source,target)
    own(app);own(root/'tmp');prepare_devices(root)
    return root


def main():
    assert not (ROOT/'claims').exists() and not (ROOT/'ready.json').exists(),'Already prepared or launched'
    protocol=json.loads((ROOT/'protocol.json').read_text())
    info=protocol['runtime_image'];archive=ROOT/info['archive']
    assert sha(archive)==info['sha256'],'Runtime archive changed'
    marker=ROOT/'template-ready.json'
    if not marker.exists():
        target=ROOT/'template';target.mkdir(exist_ok=True)
        subprocess.run(['tar','-xf',str(archive),'-C',str(target),'--no-same-owner'],check=True,timeout=600)
        save(marker,dict(sha256=info['sha256']))
    assert json.loads(marker.read_text())['sha256']==info['sha256']
    checks=[]
    for row in assignments(protocol,0):
        row=dict(row,job='fixture-v1-'+row['job'])
        os.sched_setaffinity(0,row['cpu_affinity'])
        root=make_root(row)
        env=NativeEnvironment(root,ROOT/'preflight-checkpoints'/row['job'])
        isolated=json.loads(env.probe('import os,json,socket; from pathlib import Path; '
            's=socket.socket(); network=False; '
            '\ntry: s.connect(("1.1.1.1",443)); network=True\nexcept OSError: pass\n'
            'print(json.dumps(dict(uid=os.getuid(),no_host=not Path("/mnt/lizh639").exists(),'
            'no_proc=not Path("/proc/1/environ").exists(),no_gold=not Path("/gold").exists(),no_network=not network)))'))
        assert isolated['uid']==0 and all(isolated[k] for k in ('no_host','no_proc','no_gold','no_network'))
        clean=env.execute(dict(argv=['bash','-lc','python3 -c "import os; f=os.open(\'/dev/null\',os.O_RDWR); '
            'assert os.write(f,b\'probe\')==5; assert os.read(f,1)==b\'\'; os.close(f); print(\'device-ok\')"'],
            timeout_seconds=30),time.monotonic()+30)
        assert clean.return_code==0 and clean.stdout.strip()=='device-ok' and not clean.stderr,clean
        runtime=json.loads(env.probe('import json,duckdb,pandas; import importlib.metadata as m; '
            'print(json.dumps(dict(duckdb=duckdb.__version__,pandas=pandas.__version__,dbt=m.version("dbt-duckdb"))))'))
        assert runtime==dict(duckdb='1.2.2',pandas='2.2.3',dbt='1.9.6'),runtime
        dbt=env.execute(dict(argv=['dbt','--version'],cwd=row['project'],timeout_seconds=60),time.monotonic()+60)
        assert dbt.return_code==0,dbt
        dbt_parse=env.execute(dict(argv=['dbt','parse','--profiles-dir','.'],cwd=row['project'],timeout_seconds=120),time.monotonic()+120)
        # Project parse errors are task evidence, not an unavailable dbt runtime.
        assert not dbt_parse.timed_out and not dbt_parse.blocked,dbt_parse
        checkpoint=env.checkpoint('fixture-baseline')
        env.execute(dict(argv=['python3','-c','from pathlib import Path; Path("fixture.txt").write_text("x")']),time.monotonic()+30)
        env.restore(checkpoint);assert not (root/'app/fixture.txt').exists()
        env.outcome_reliability=True
        failure=env.execute(dict(argv=['bash','-lc','false | true']),time.monotonic()+30)
        assert failure.return_code==0 and failure.execution_observation['nonzero_statuses'],failure
        spec=ROOT/'fixtures'/(row['job']+'-spec.json');save(spec,row)
        completed=subprocess.run([PYTHON,'-B',str(ROOT/'fixture_runner.py'),str(spec)],
            env=dict(os.environ,LONGCLI_METHOD=row['method']),capture_output=True,text=True,check=True,timeout=180)
        summary=json.loads(completed.stdout.strip().splitlines()[-1])
        assert summary['submitted'] and summary['tool_calls']==1 and summary['fixture'],summary
        assert sha(ROOT/'fixtures'/row['job']/'source.tar.gz')==summary['artifact']['sha256']
        checks.append(dict(task=row['task'],isolation=isolated,runtime=runtime,device_clean=True,
            checkpoint_restore=True,masked_failure_detected=True,dbt_version_ok=True,
            project_parse_exit=dbt_parse.return_code,project_parse_stderr=dbt_parse.stderr[-1000:],
            fixture=summary,model_calls=0))
        print(json.dumps(dict(task=row['task'],checked=True,model_calls=0)),flush=True)
    save(ROOT/'preflight-0.json',dict(passed=True,checks=checks,model_calls=0))
    files=list(ROOT.glob('*.py'))+[ROOT/'protocol.json',ROOT/'data-provenance.json']
    files += [p for name in ('sources','compatibility','public') for p in (ROOT/name).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    save(ROOT/'ready.json',dict(ready=True,model_calls=0,
        hashes={p.relative_to(ROOT).as_posix():sha(p) for p in files}))
    print(json.dumps(dict(ready=True,sealed_files=len(files),model_calls=0)),flush=True)


if __name__=='__main__':main()
