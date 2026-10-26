import errno,json,tempfile,unittest,types,sys
from pathlib import Path
from unittest.mock import patch
import campaign as c

class CampaignTests(unittest.TestCase):
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
                (live/'wall-limit.json').write_text('{"reason":"solver_wall_limit_3h","limit_seconds":10800}')
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
            return Process()
        proxy=types.SimpleNamespace(ThreadingHTTPServer=Proxy,HOST='127.0.0.1',Handler=None)
        with tempfile.TemporaryDirectory() as d,patch.object(c,'ROOT',Path(d)),patch.object(c,'validate'),patch.object(c,'space_ready',return_value=True),patch.object(c.time,'sleep'),patch.object(c.subprocess,'Popen',side_effect=popen),patch.object(c,'trial',return_value=dict(engineering_clean=True,reward=0)),patch.dict(sys.modules,network_proxy=proxy):
            Path(d,'tasks.json').write_text(json.dumps(dict(tasks=[dict(name=str(n)) for n in range(30)])))
            Path(d,'history.json').write_text('{}');c.supervise();state=json.loads(Path(d,'health.json').read_text())
            self.assertEqual(state['state'],'finished');self.assertEqual(state['summary']['kz-dsh']['first_finished'],30)
            self.assertEqual(state['summary']['kz-dsh']['retry_total'],1)
            first_retry=next(i for i,j in enumerate(launched) if 'retry-' in j)
            self.assertTrue(all('first-' not in j for j in launched[first_retry:]))

if __name__=='__main__':unittest.main()
