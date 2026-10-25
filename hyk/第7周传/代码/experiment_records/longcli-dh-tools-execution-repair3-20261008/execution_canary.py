"""Three concurrent owned Docker fixtures, including killed driver; zero API."""
import json,multiprocessing,time
from pathlib import Path
from common import ROOT,save,export_tree
from docker_environment import DockerEnvironment,TaskBackendError,close_owned

def run_fixture(number):
    p=json.loads((ROOT/'protocol.json').read_text());row=p['tasks'][number]
    d=ROOT/'acceptance-jobs'/('execution-canary-'+str(number)+'-'+str(time.time_ns()));d.mkdir()
    try:
        env=DockerEnvironment(row,d)
        n=env.execute({'argv':['sh','-c','nproc'],'timeout_seconds':10},time.monotonic()+15)
        assert n.return_code==0 and int(n.stdout)==2,n
        # A task's files must not shadow Python libraries used by the harness.
        (env.workspace/'json.py').write_text('raise RuntimeError("TASK_SHADOW")')
        assert env.probe('print("ISOLATED_IMPORT_OK")')=='ISOLATED_IMPORT_OK'
        if number==0:
            cmd={'argv':['python3','-I','-c',
                'import os;from pathlib import Path;Path("executed-once").write_text("once");os.kill(os.getppid(),9)'],
                'timeout_seconds':10}
            try:env.execute(cmd,time.monotonic()+15)
            except TaskBackendError:pass
            else:raise AssertionError('killed driver was not classified as task-local')
            assert (env.workspace/'executed-once').read_text()=='once'
            close_owned(d)
            artifact=export_tree(env.workspace,d/'final-source.tar.gz',source_only=True)
            return {'fixture':number,'state':'local_failure_preserved','artifact':artifact['sha256'],
                    'visible_cpus':2,'paid_model_calls':0}
        r=env.execute({'argv':['sh','-c','printf HEALTHY_TASK'],'timeout_seconds':10},time.monotonic()+15)
        assert r.return_code==0 and r.stdout=='HEALTHY_TASK'
        return {'fixture':number,'state':'healthy_completed','visible_cpus':2,'paid_model_calls':0}
    finally:close_owned(d)

def main():
    with multiprocessing.get_context('fork').Pool(3) as pool:rows=pool.map(run_fixture,range(3))
    assert [r['state'] for r in rows]==['local_failure_preserved','healthy_completed','healthy_completed']
    save(ROOT/'evidence/execution-canary.json',{'passed':True,'concurrency':3,'fixtures':rows,'paid_model_calls':0})
    print(json.dumps({'passed':True,'concurrency':3,'fixtures':rows,'paid_model_calls':0}))

if __name__=='__main__':main()
