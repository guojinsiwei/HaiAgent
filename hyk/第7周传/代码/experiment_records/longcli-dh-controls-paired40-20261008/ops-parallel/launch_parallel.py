"""Fresh hidden credential -> RAM-only replacement controller; no solver source edits."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from identity import process_status
OPS=Path(__file__).resolve().parent
ROOT=OPS.parent


def validate_ops():
    ready=json.loads((OPS/'ready.json').read_text())
    assert ready['passed'] and ready['paid_model_calls']==0
    for name,value in ready['hashes'].items():
        assert hashlib.sha256((OPS/name).read_bytes()).hexdigest()==value


def main():
    validate_ops();sys.path.insert(0,str(ROOT))
    from common import validate,save
    p=validate();h=json.loads((ROOT/'health.json').read_text());state=process_status(h.get('pid'),ROOT)
    assert state['status']=='running' and b'run_worker.py' in (Path('/proc')/str(h['pid'])/'cmdline').read_bytes()
    assert not h.get('fatal') and not h.get('errors') and not (OPS/'launch.claim').exists()
    if '--check' in sys.argv:
        print(json.dumps(dict(ready=True,keep_existing_tasks=True,concurrency=p['concurrency'],
            concurrency_per_arm=p['concurrency_per_arm'],solver_source_unchanged=True)));return
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    from net_transport import request
    result=request('https://api.deepseek.com/models',None,key,30)
    assert result[0]=='ok' and any(m['id']==p['model'] for m in json.loads(result[1])['data'])
    os.close(os.open(OPS/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    with (OPS/'worker.log').open('x') as out,(OPS/'worker-stderr.log').open('x') as err:
        child=subprocess.Popen([sys.executable,'-B',str(OPS/'resume_worker.py'),str(ROOT)],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
        child.stdin.write(key+'\n');child.stdin.close()
    save(OPS/'launch.json',dict(pid=child.pid,time=time.time(),credential='fresh encrypted stdin; RAM only',
        solver_source_unchanged=True,concurrency=12,concurrency_per_arm=6))
    print(json.dumps(dict(handoff_started=True,pid=child.pid,concurrency=12,task_restarts=0)))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(state='handoff_launch_failed',error_type=type(error).__name__)))
        raise SystemExit(1)
