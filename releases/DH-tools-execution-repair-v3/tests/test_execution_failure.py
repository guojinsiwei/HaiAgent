"""No credentials/network: execution failures must never replay a side effect."""
import json,sys,time,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import environment
import docker_environment as de
from runner import ObservedRunner,preserve_task

class ExecutionTests(unittest.TestCase):
    def test_dead_driver_is_local_and_not_retried(self):
        calls=[]
        def fake(*args,**kwargs):
            calls.append(args)
            if args[0]=='exec':return SimpleNamespace(returncode=137,stdout='',stderr='killed')
            return SimpleNamespace(returncode=0,stdout=json.dumps([{'State':{'Running':True,'OOMKilled':False}}]),stderr='')
        with tempfile.TemporaryDirectory() as folder,patch.object(de,'docker',side_effect=fake):
            d=Path(folder)
            with self.assertRaises(de.TaskBackendError):
                de.DockerExecutor('owned',d).execute({'argv':['sh','-c','touch once']},time.monotonic()+10)
            self.assertEqual(sum(c[0]=='exec' and '-i' in c for c in calls),1)
            receipt=json.loads(next(d.glob('execution-fault-*.json')).read_text())
            self.assertEqual(receipt['scope'],'task')
            self.assertEqual(receipt['automatic_action_retries'],0)
            self.assertEqual(receipt['command_completion'],'unknown')
            self.assertIn('-I',calls[0])
    def test_container_loss_local_daemon_loss_shared(self):
        for daemon_code,exception in [(0,de.TaskBackendError),(1,de.SharedBackendError)]:
            replies=[SimpleNamespace(returncode=1,stdout='',stderr='missing'),
                     SimpleNamespace(returncode=daemon_code,stdout='',stderr='unavailable')]
            with patch.object(de,'docker',side_effect=replies):
                with self.assertRaises(exception):de.execution_fault('owned',None,137,'killed')
    def test_infrastructure_event_does_not_publish_premature_fleet_stop(self):
        from bestfgs.code_tools import ToolTaskRunner
        obj=object.__new__(ObservedRunner);obj.health={};obj.counts={'tool_calls':1,'model_requests':1}
        with tempfile.TemporaryDirectory() as folder,patch.object(ToolTaskRunner,'_emit'):
            obj.directory=Path(folder)
            obj._emit('infrastructure_error',error_type='TaskBackendError')
            self.assertNotIn('engineering_fault',obj.health)
            self.assertEqual(obj.health['task_error_pending'],'TaskBackendError')
    def test_local_failure_stops_owned_container_before_export(self):
        order=[]
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);(d/'workspace').mkdir();h={}
            with patch('runner.close_owned',side_effect=lambda d:order.append('stop')),\
                 patch('runner.export_tree',side_effect=lambda *a,**k:order.append('export') or {'sha256':'fixture'}):
                preserve_task(d,h)
            self.assertEqual(order,['stop','export'])
            self.assertEqual(h['state'],'awaiting_grade')

    def test_scheduler_continues_after_failed_pilot(self):
        import runner
        protocol={'methods':['dh_tools'],'tasks':[{'task':str(i)} for i in range(5)],
                  'wall_seconds':7200,'concurrency':3,'concurrency_per_arm':3}
        class Process:
            pid=999999
            def __init__(self,target,args):self.row=args[0]
            def start(self):
                d=runner.ROOT/'jobs'/('dh_tools--'+self.row['task']);d.mkdir(parents=True)
                status={'state':'awaiting_grade','updated':time.time()}
                if self.row['task']=='0':status['task_local_error']='TaskBackendError'
                runner.save(d/'summary.json',status);runner.save(d/'health.json',status)
            def is_alive(self):return False
            def join(self,*args):pass
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(runner,'ROOT',root),patch.object(runner,'validate',return_value=protocol),\
                 patch.object(runner.multiprocessing,'get_context',return_value=SimpleNamespace(Process=Process)),\
                 patch.object(runner.subprocess,'Popen',return_value=SimpleNamespace(pid=999998,poll=lambda:None)),\
                 patch.object(runner.time,'sleep'),patch.dict(runner.os.environ):
                import tempfile as tf
                with patch.object(tf,'tempdir',None):runner.worker('fixture-only')
            h=json.loads((root/'health.json').read_text())
            self.assertEqual(h['state'],'generation_complete')
            self.assertEqual(len(h['completed']),5)
            self.assertFalse(h['pending']);self.assertIsNone(h['fatal'])

if __name__=='__main__':unittest.main()
