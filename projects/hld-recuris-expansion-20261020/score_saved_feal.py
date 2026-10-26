"""Grade the frozen FEAL submission once, with original tests/resources/deadline."""
from pathlib import Path
from types import SimpleNamespace
import asyncio, hashlib, json, shutil, sqlite3, subprocess, time
from storage import atomic_json
from verifier_setup import prepare_verifier, verifier_network, validate_test_report

R = Path(__file__).resolve().parent
A = R / 'feal-regrade-20261021'
JOB = 'tb2hr50-42-recuris-feal-differential-cryptanalysis'
NAME = 'tb2hr50-feal-artifact-regrade'

def calls():
    with sqlite3.connect(R / 'spending.sqlite', timeout=20) as db:
        return db.execute('select count(*) from calls where job=?', (JOB,)).fetchone()[0]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def text(value):
    return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')

class Environment:
    async def upload_file(self, source, target):
        subprocess.run(['docker','cp',str(source),NAME+':'+target],check=True,capture_output=True)
    async def exec(self, command, user='root', env=None, timeout_sec=900):
        args=['docker','exec','-u',user]
        for k,v in (env or {}).items():args+=['-e',k+'='+str(v)]
        p=subprocess.run(args+[NAME,'bash','-c',command],capture_output=True,text=True,timeout=timeout_sec)
        return SimpleNamespace(return_code=p.returncode,stdout=p.stdout,stderr=p.stderr)

async def main():
    with (A/'launch-once.marker').open('x') as stream:stream.write(str(time.time()))
    trial=next((R/'jobs'/JOB).glob('*/submission-snapshot.json')).parent
    snapshot=json.loads((trial/'submission-snapshot.json').read_text())
    task=R/'dependencies/official/tasks/feal-differential-cryptanalysis'
    original_result_hash=digest(trial/'result.json')
    hashes={str(p.relative_to(task/'tests')):digest(p) for p in (task/'tests').rglob('*') if p.is_file()}
    tests=A/'tests';shutil.copytree(task/'tests',tests)
    out=A/'verifier';out.mkdir()
    before_calls=calls()
    result=dict(source_trial=str(trial),snapshot_image=snapshot['image_id'],original_result_sha256=original_result_hash,
        official_test_hashes=hashes,paid_calls=0,original_calls_before=before_calls,
        timeout_seconds=1800,cpu_limit=1,memory_gib=2,solver_rerun=False)
    atomic_json(A/'provenance.json',result)
    atomic_json(A/'health.json',dict(state='preparing',updated=time.time(),paid_calls=0))
    subprocess.run(['docker','run','-d','--name',NAME,'--label','experiment='+R.name,
        '--network','bridge','--cpus','1','--memory','2g','--pids-limit','512','--user','root',
        '--entrypoint','sleep','--mount','type=bind,src='+str(tests)+',dst=/tests',
        '--mount','type=bind,src='+str(out)+',dst=/logs/verifier',
        snapshot['image_id'],'infinity'],check=True,capture_output=True)
    verifier=SimpleNamespace(task=SimpleNamespace(paths=SimpleNamespace(task_dir=task)),
        trial_paths=SimpleNamespace(verifier_dir=out),environment=Environment(),verifier_env={})
    started=time.time()
    try:
        with verifier_network(verifier):
            await prepare_verifier(verifier)
            started=time.time()
            atomic_json(A/'health.json',dict(state='verifying',started=started,updated=started,paid_calls=0,container=NAME))
            try:
                p=await verifier.environment.exec('bash /tests/test.sh',env=verifier.verifier_env,timeout_sec=1800)
                (out/'test-stdout.txt').write_text(p.stdout)
                (out/'test-stderr.txt').write_text(p.stderr)
                validate_test_report(verifier)
                report=json.loads((out/'ctrf.json').read_text())['results']
                reward=int((out/'reward.txt').read_text().strip());assert reward in (0,1)
                result.update(engineering_clean=True,reward=reward,tests=report['summary'],exit_code=p.return_code)
            except subprocess.TimeoutExpired as error:
                (out/'test-stdout.txt').write_text(text(error.stdout))
                (out/'test-stderr.txt').write_text(text(error.stderr))
                result.update(engineering_clean=False,reward=None,error_type='VerifierTimeoutError',
                    failure_classification='submission_runtime_timeout',
                    evidence='Official test invokes unchanged attack.attack; saved submission scans up to 65536*65536 inputs inside each candidate check')
    except Exception as error:
        result.update(engineering_clean=False,reward=None,error_type=type(error).__name__,error=str(error)[:500])
    finally:
        subprocess.run(['docker','stop','-t','2',NAME],capture_output=True)
        result.update(elapsed=time.time()-started,original_calls_after=calls())
        result['paid_calls']=result['original_calls_after']-before_calls
        result['original_result_unchanged']=digest(trial/'result.json')==original_result_hash
        result['official_tests_unchanged']=all(digest(task/'tests'/p)==d and digest(tests/p)==d for p,d in hashes.items())
        if result['paid_calls']!=0 or not result['original_result_unchanged'] or not result['official_tests_unchanged']:
            result.update(engineering_clean=False,validation_failed=True)
        atomic_json(A/'result.json',result)
        atomic_json(A/'health.json',dict(state='finished',updated=time.time(),result=result))
    print(json.dumps(result),flush=True)

if __name__=='__main__':asyncio.run(main())
