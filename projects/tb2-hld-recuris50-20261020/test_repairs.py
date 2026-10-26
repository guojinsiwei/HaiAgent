import asyncio,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from budget_classification import MESSAGE,hld_monetary_stop
from submission_snapshot import snapshot
import lifecycle_guard as lg

class BudgetTests(unittest.TestCase):
    def test_budget_requires_terminal_structured_event_and_valid_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);f=p/'dsh.jsonl'
            event={'type':'status','phase':'turn_end','reason':{'kind':'error','error':{'message':MESSAGE}}}
            f.write_text(json.dumps(event)+'\n')
            self.assertTrue(hld_monetary_stop(p,'hld',True,1))
            for arm,valid,code in [('recuris',True,1),('hld',False,1),('hld',True,137)]:
                self.assertFalse(hld_monetary_stop(p,arm,valid,code))
            f.write_text(json.dumps({'type':'text','text':MESSAGE})+'\n')
            self.assertFalse(hld_monetary_stop(p,'hld',True,1))
            f.write_text(json.dumps(event)+'\n'+json.dumps({'type':'status','phase':'turn_end','reason':{'kind':'error','error':{'message':'real failure'}}})+'\n')
            self.assertFalse(hld_monetary_stop(p,'hld',True,1))

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_collection_retains_only_its_own_environment(self):
        class FakeTrial:
            _collect_artifacts_phased=AsyncMock()
            _run_collect_hooks=AsyncMock()
            _verify_with_timeout=AsyncMock()
            async def _finalize(self):self.finalized=True
        class FakeEnv:
            stop_service=AsyncMock()
            _run_docker_compose_command=AsyncMock()
            service_exec=AsyncMock()
            service_is_dir=AsyncMock()
            prepare_logs_for_host=AsyncMock()
        class FakeArtifacts:
            _download_artifact=AsyncMock()
        lg.install(FakeTrial,FakeEnv,FakeArtifacts)
        with tempfile.TemporaryDirectory() as d:
            for failed in [True,False]:
                t=FakeTrial();t.agent_environment=SimpleNamespace(_keep_containers=False)
                t.paths=SimpleNamespace(trial_dir=Path(d))
                t._kz_lifecycle={'schema_version':2,'events':[],'failures':[{'kind':'test'}] if failed else []}
                await t._finalize()
                self.assertTrue(t.finalized)
                self.assertEqual(t.agent_environment._keep_containers,failed)

    async def test_snapshot_includes_stopped_container(self):
        with tempfile.TemporaryDirectory() as d:
            env=SimpleNamespace(_run_docker_compose_command=AsyncMock(return_value=SimpleNamespace(stdout='abc\n')))
            trial=SimpleNamespace(agent_environment=env,paths=SimpleNamespace(trial_dir=Path(d)))
            process=SimpleNamespace(returncode=0,communicate=AsyncMock(return_value=(b'sha256:abc',b'')))
            with patch.dict('os.environ',{'SCORE_SNAPSHOT_ACCEPTANCE':'1','PAIRED_ATTEMPT_ID':'test'}),patch('submission_snapshot.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
                await snapshot(trial)
            self.assertEqual(env._run_docker_compose_command.call_args.args[0],['ps','-a','-q','main'])
            self.assertEqual(json.loads((Path(d)/'submission-snapshot.json').read_text())['container_id'],'abc')

    async def test_handoff_rejects_unrelated_mount(self):
        env=SimpleNamespace(prepare_logs_for_host=AsyncMock(),_run_docker_compose_command=AsyncMock(return_value=SimpleNamespace(return_code=1)))
        doc={'State':{'Running':False},'Mounts':[{'Type':'bind','Destination':'/logs/agent','Source':'/different-trial'}]}
        with patch('lifecycle_guard.main_container',AsyncMock(return_value=doc)),patch('lifecycle_guard.asyncio.create_subprocess_exec',AsyncMock()) as spawn:
            with self.assertRaises(lg.CollectionFailure):await lg.handoff_logs(env,Path('/expected-trial'))
            spawn.assert_not_called()

    async def test_handoff_uses_isolated_helper_without_restarting_main(self):
        with tempfile.TemporaryDirectory() as d:
            env=SimpleNamespace(prepare_logs_for_host=AsyncMock(),_run_docker_compose_command=AsyncMock(return_value=SimpleNamespace(return_code=1)))
            doc={'State':{'Running':False},'Image':'sha256:abc','Mounts':[{'Type':'bind','Destination':'/logs/agent','Source':d}]}
            process=SimpleNamespace(returncode=0,communicate=AsyncMock(return_value=(b'',b'')))
            with patch('lifecycle_guard.main_container',AsyncMock(return_value=doc)),patch('lifecycle_guard.asyncio.create_subprocess_exec',AsyncMock(return_value=process)) as spawn:
                await lg.handoff_logs(env,Path(d))
                args=spawn.call_args.args
                self.assertIn('--network',args);self.assertIn('none',args);self.assertIn('--read-only',args)
                self.assertNotIn('start',args)

if __name__=='__main__':unittest.main()
