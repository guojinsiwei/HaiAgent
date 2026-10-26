import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
import lifecycle_guard as guard

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);(root/'agent').mkdir();(root/'artifacts').mkdir()
        self.order=[];order=self.order
        class Env:
            async def prepare_logs_for_host(s):order.append('handoff')
            async def stop_service(s,service):
                order.append('stop:'+service);return await s._run_docker_compose_command(['stop',service])
            async def _run_docker_compose_command(s,command,**kw):order.append(tuple(command))
            async def service_exec(s,command,*,service=None,**kw):
                order.append('hook:'+str(service));return N(return_code=0 if command=='ok' else 1)
        class Handler:
            async def _download_artifact(s,*,source_env,artifacts_dir,artifact,convention_source):
                order.append('download:'+str(artifact.service));return artifact
        class Trial:
            async def _run_collect_hooks(s,hooks):
                await s.agent_environment.service_exec(s.hook,service='kafka')
            async def _collect_artifacts_phased(s,*,artifacts_dir,**kw):
                await s.agent_environment.stop_service(s.stop)
                await s._run_collect_hooks([])
                # Harbor's service_is_dir probe returns 1 for a FILE. This is
                # not a failed collect hook and must not poison the outcome.
                await s.agent_environment.service_exec('test -d snapshot.tgz',service='kafka')
                await Handler()._download_artifact(source_env=s.agent_environment,artifacts_dir=artifacts_dir,
                    artifact=s.artifact,convention_source='/artifacts')
            async def _verify_with_timeout(s,*a,**kw):order.append('verify');return 0
            async def _finalize(s):await s.agent_environment._run_docker_compose_command(['down'])
        guard.install(Trial,Env,Handler)
        self.t=Trial();self.t.paths=N(trial_dir=root,agent_dir=root/'agent')
        self.t.agent_environment=Env();self.t.stop='main';self.t.hook='ok'
        self.t.artifact=N(service='kafka',status='ok',type='file',destination='artifacts/snapshot.tgz')
        (root/'artifacts/snapshot.tgz').write_bytes(b'fixture snapshot')
    async def collect(self):await self.t._collect_artifacts_phased(artifacts_dir=self.t.paths.trial_dir/'artifacts')
    async def test_handoff_before_stop_sidecar_collected_before_verify_and_cleanup(self):
        await self.collect();self.assertEqual(await self.t._verify_with_timeout(None,1),0);await self.t._finalize()
        self.assertLess(self.order.index('handoff'),self.order.index('stop:main'))
        self.assertLess(self.order.index('download:kafka'),self.order.index('verify'))
        self.assertEqual(self.order[-1],('down','--volumes'))
        self.assertEqual(self.t._kz_lifecycle['failures'],[])
    async def test_sidecar_nonzero_records_fault_refuses_grading_but_allows_cleanup(self):
        self.t.hook='failed'
        with self.assertRaises(guard.CollectionFailure):await self.collect()
        with self.assertRaises(guard.CollectionFailure):await self.t._verify_with_timeout(None,1)
        await self.t._finalize();self.assertNotIn('verify',self.order)
        self.assertEqual(self.t._kz_lifecycle['failures'][0]['kind'],'sidecar_collect_hook')
    async def test_empty_sidecar_file_is_engineering_failure(self):
        (self.t.paths.trial_dir/'artifacts/snapshot.tgz').write_bytes(b'')
        with self.assertRaises(guard.CollectionFailure):await self.collect()
    async def test_premature_sidecar_stop_rejected(self):
        self.t.stop='kafka'
        with self.assertRaises(guard.CollectionFailure):await self.collect()
        self.assertNotIn('stop:kafka',self.order)
    async def test_unreadable_logs_fail_before_main_stop(self):
        with patch.object(guard,'readable_logs',side_effect=PermissionError):
            with self.assertRaises(PermissionError):await self.collect()
        self.assertNotIn('stop:main',self.order)
        self.assertEqual(self.t._kz_lifecycle['failures'][0]['kind'],'collection_or_log_handoff')
    async def test_missing_main_output_remains_a_grader_outcome(self):
        self.t.artifact.service=None;self.t.artifact.status='failed'
        await self.collect();self.assertEqual(await self.t._verify_with_timeout(None,1),0)
    async def test_cross_trial_context_resets_after_failure(self):
        self.t.hook='failed'
        with self.assertRaises(guard.CollectionFailure):await self.collect()
        self.assertIsNone(guard.CURRENT.get())

if __name__=='__main__':unittest.main()
