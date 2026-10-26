import errno,json,tempfile,unittest,types,sys
from pathlib import Path
from unittest.mock import patch
import campaign as c
from test_engineering import lifecycle

class FakeBudget:
    def __init__(self,*a,**kw):self.url='http://offline.invalid';self.token='fixture'
    def snapshot(self):return {'halt_reason':None}
    def close(self):pass

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.budget_patch=patch.object(c,'BudgetService',FakeBudget);self.budget_patch.start();self.addCleanup(self.budget_patch.stop)

    def test_enospc_checkpoint_holds_admission_until_durable(self):
        with patch.object(c,'save',side_effect=[OSError(errno.ENOSPC,'full'),None]) as save:
            sleeps=[];c.durable('test',{},sleep=sleeps.append)
            self.assertEqual(save.call_count,2);self.assertEqual(sleeps,[10])
    def test_missing_final_keeps_all_http_attempts(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)):
            p=Path(d)/'jobs/j/t';live=p/'agent/live';live.mkdir(parents=True)
            (p/'config.json').write_text('{}')
            (live/'route.jsonl').write_text('\n'.join(json.dumps(x) for x in [dict(event='request_shape'),dict(event='transport_error'),dict(event='request_shape'),dict(event='response',status=200)]))
            result=c.trial(dict(job='j'));self.assertFalse(result['engineering_clean']);self.assertEqual(result['actual_http_attempts'],2)
    def test_common_budget_is_outcome_but_collection_or_auth_failure_is_not(self):
        for failure in ('none','collection','auth'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)):
                p=Path(d)/'jobs/j/t';live=p/'agent/live';live.mkdir(parents=True)
                (p/'result.json').write_text('{"verifier_result":{"rewards":{"reward":0}}}')
                (live/'agent-exit.json').write_text('{"exit_code":143,"timed_out":true}')
                (live/'wall-limit.json').write_text('{"state":"enforced","reason":"solver_wall_limit","limit_seconds":2700}')
                (p/'lifecycle.json').write_text(json.dumps(lifecycle()))
                if failure=='collection':(p/'lifecycle.json').write_text('{"failures":[{"kind":"sidecar_collect_hook"}]}')
                if failure=='auth':(live/'route.jsonl').write_text('{"event":"response","status":401}')
                result=c.trial(dict(job='j'));self.assertEqual(result['engineering_clean'],failure=='none')
    def test_invalid_solver_exit_keeps_grade_and_flags_engineering(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)):
            p=Path(d)/'jobs/j/t';(p/'agent/live').mkdir(parents=True)
            (p/'result.json').write_text('{"verifier_result":{"rewards":{"reward":0}}}')
            (p/'agent/live/agent-exit.json').write_text('{"exit_code":137}')
            result=c.trial(dict(job='j'));self.assertFalse(result['engineering_clean']);self.assertEqual(result['reward'],0)
    def test_actual_supervisor_continues_30_after_launch_fault_then_retries_last(self):
        launched=[]
        class Process:
            pid=123;returncode=0
            def poll(self):return 0
            def wait(self):return 0
        class Proxy:
            def __init__(self,*a):pass
            def serve_forever(self):pass
            def shutdown(self):pass
        def popen(cmd,**kw):
            job=cmd[cmd.index('--job-name')+1];launched.append(job)
            if len(launched)==1:raise OSError('per-task launch failure')
            attempt=kw['env']['PAIRED_ATTEMPT_ID']
            c.atomic_json(c.ROOT/'attempts'/(attempt+'.json'),dict(schema_version=1,attempt_id=attempt,state='completed',harbor_exit=0))
            return Process()
        proxy=types.SimpleNamespace(ThreadingHTTPServer=Proxy,HOST='127.0.0.1',Handler=None)
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)),patch.object(c,'validate'),patch.object(c,'space_ready',return_value=True),patch.object(c.time,'sleep'),patch.object(c.subprocess,'Popen',side_effect=popen),patch.object(c,'trial',return_value=dict(engineering_clean=True,reward=0)),patch.object(c,'proxy_module',return_value=proxy):
            Path(d,'tasks.json').write_text(json.dumps(dict(tasks=[dict(name=str(n)) for n in range(30)])))
            Path(d,'history.json').write_text('{}');c.supervise();state=json.loads(Path(d,'health.json').read_text())
            self.assertEqual(state['state'],'finished');self.assertEqual(state['summary']['kz-dsh']['first_finished'],30)
            self.assertEqual(state['summary']['kz-dsh']['retry_total'],0)
            self.assertFalse(any('retry-' in j for j in launched))

    def test_single_task_authentication_failure_continues_and_preserves_costs(self):
        launched=[]
        class Process:
            pid=123;returncode=0
            def poll(self):return 0
            def wait(self):return 0
        class Proxy:
            def __init__(self,*a):pass
            def serve_forever(self):pass
            def shutdown(self):pass
        def popen(cmd,**kw):
            job=cmd[cmd.index('--job-name')+1];launched.append(job)
            attempt=kw['env']['PAIRED_ATTEMPT_ID']
            c.atomic_json(c.ROOT/'attempts'/(attempt+'.json'),dict(schema_version=1,attempt_id=attempt,state='completed',harbor_exit=0))
            return Process()
        def collect(row,offline):
            auth=not offline and row['task']=='a' and row['stage']=='first'
            return dict(engineering_clean=not auth,reward=0,auth_failure=auth,requests=1)
        def pause(_):
            state=c.read(c.ROOT/'admissions.json')
            if state['state']=='held_authentication':
                c.atomic_json(c.ROOT/'control.json',dict(command='drain',supervisor_identity=None))
        proxy=types.SimpleNamespace(ThreadingHTTPServer=Proxy,HOST='127.0.0.1',Handler=None)
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)),patch.object(c,'validate'),patch.object(c,'process_identity',return_value=None),patch.object(c,'space_ready',return_value=True),patch.object(c.time,'sleep',side_effect=pause),patch.object(c.subprocess,'Popen',side_effect=popen),patch.object(c,'trial',side_effect=collect),patch.object(c,'proxy_module',return_value=proxy):
            Path(d,'tasks.json').write_text(json.dumps(dict(tasks=[dict(name=n) for n in ('a','b')])))
            Path(d,'history.json').write_text('{}')
            c.supervise()
            before=c.read(c.ROOT/'admissions.json')
            self.assertEqual(before['state'],'finished')
            self.assertEqual(before['rows'][0]['result']['requests'],1)
            self.assertEqual(before['rows'][1]['state'],'done')
            # A real new supervisor has a different PID/start identity. The
            # test explicitly removes its consumed synthetic drain request.
            (c.ROOT/'control.json').unlink(missing_ok=True)
            c.supervise(resume=True)
            after=c.read(c.ROOT/'admissions.json')
            self.assertEqual(after['state'],'finished')
            self.assertEqual(after['rows'][0]['result']['requests'],1)
            self.assertEqual(after['summary']['kz-dsh']['retry_total'],0)
            self.assertEqual(launched.count('first-01-kz-dsh-a'),1)
            self.assertEqual(launched.count('first-02-kz-dsh-b'),1)

    def test_missing_runner_receipt_holds_dispatch_instead_of_retrying(self):
        launched=[]
        class Process:
            pid=123;returncode=1
            def poll(self):return 1
            def wait(self):return 1
        class Proxy:
            def __init__(self,*a):pass
            def serve_forever(self):pass
            def shutdown(self):pass
        def popen(cmd,**kw):launched.append(cmd);return Process()
        def pause(_):
            state=c.read(c.ROOT/'admissions.json')
            if state['state']=='held_reconciliation':
                c.atomic_json(c.ROOT/'control.json',dict(command='drain',supervisor_identity=None))
        proxy=types.SimpleNamespace(ThreadingHTTPServer=Proxy,HOST='127.0.0.1',Handler=None)
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)),patch.object(c,'validate'),patch.object(c,'process_identity',return_value=None),patch.object(c,'space_ready',return_value=True),patch.object(c.time,'sleep',side_effect=pause),patch.object(c.subprocess,'Popen',side_effect=popen),patch.object(c,'proxy_module',return_value=proxy):
            Path(d,'tasks.json').write_text(json.dumps(dict(tasks=[dict(name=n) for n in ('a','b')])))
            Path(d,'history.json').write_text('{}');c.supervise()
            state=c.read(c.ROOT/'admissions.json')
            self.assertEqual(len(launched),1)
            self.assertEqual(state['rows'][0]['state'],'reconciliation_required')
            self.assertEqual(state['rows'][1]['state'],'pending')
            self.assertEqual(state['summary']['kz-dsh']['retry_total'],0)

    def test_total_budget_stop_does_not_write_container_owned_directory(self):
        launched=[]
        class Budget(FakeBudget):
            def snapshot(self):return {'halt_reason':'campaign_budget_exhausted' if launched else None}
        class Process:
            pid=123;returncode=0
            def poll(self):return 0
            def wait(self):return 0
        class Proxy:
            def __init__(self,*a):pass
            def serve_forever(self):pass
            def shutdown(self):pass
        write=c.atomic_json
        def guarded_write(path,value):
            if 'live' in Path(path).parts:raise PermissionError('container owned')
            return write(path,value)
        def popen(cmd,**kw):
            job=cmd[cmd.index('--job-name')+1];launched.append(job)
            (c.ROOT/'jobs'/job/'trial/agent/live').mkdir(parents=True)
            attempt=kw['env']['PAIRED_ATTEMPT_ID']
            write(c.ROOT/'attempts'/(attempt+'.json'),dict(schema_version=1,attempt_id=attempt,state='completed',harbor_exit=0))
            return Process()
        proxy=types.SimpleNamespace(ThreadingHTTPServer=Proxy,HOST='127.0.0.1',Handler=None)
        rows=[dict(task=n,job=n,arm='kz-dsh',stage='first',state='pending',preflight_ok=True) for n in ('a','b')]
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)),patch.object(c,'BudgetService',Budget),patch.object(c,'validate'),patch.object(c,'initial_rows',return_value=rows),patch.object(c,'space_ready',return_value=True),patch.object(c.time,'sleep'),patch.object(c.subprocess,'Popen',side_effect=popen),patch.object(c,'trial',return_value=dict(engineering_clean=True,reward=0)),patch.object(c,'proxy_module',return_value=proxy),patch.object(c,'atomic_json',side_effect=guarded_write):
            Path(d,'tasks.json').write_text('{"tasks":[]}');Path(d,'history.json').write_text('{}')
            c.supervise();state=c.read(Path(d)/'health.json')
            self.assertEqual(launched,['a'])
            self.assertEqual(state['state'],'held_budget_or_provider')
            self.assertEqual(state['rows'][1]['state'],'pending')

if __name__=='__main__':unittest.main()
