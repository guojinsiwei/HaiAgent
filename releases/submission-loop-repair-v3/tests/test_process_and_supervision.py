import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'integration'), str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/hai-project/src')]
from docker_state import DockerState


class ProcessStatusTests(unittest.TestCase):
    def state(self, output):
        state = DockerState.__new__(DockerState)
        state.process_baselines = {'owned': frozenset({101, 102})}
        state.owned_container = lambda ident: None
        state.docker = lambda *a, **k: output
        return state

    def test_zombie_not_mistaken_for_live_detached_process(self):
        self.state('PID PPID STAT\n101 0 S\n102 101 S\n103 101 Z\n').ensure_idle('owned')

    def test_live_detached_process_refused(self):
        state = self.state('PID PPID STAT\n101 0 S\n102 101 S\n103 101 S\n')
        with patch('docker_state.time.sleep'), self.assertRaisesRegex(RuntimeError, 'Detached live'):
            state.ensure_idle('owned')

    def test_missing_bootstrap_or_unknown_process_table_refused(self):
        for output in ('PID PPID STAT\n101 0 S\n', 'garbled', 'PID PPID STAT\n101 x S\n'):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                self.state(output).ensure_idle('owned')

    def test_process_exit_race_gets_bounded_wait_not_command_replay(self):
        state = self.state('')
        replies = iter(['PID PPID STAT\n101 0 S\n102 101 S\n103 101 R\n',
                        'PID PPID STAT\n101 0 S\n102 101 S\n'])
        calls = []
        def docker(*args, **kw):
            calls.append(args); return next(replies)
        state.docker = docker
        with patch('docker_state.time.sleep'):
            state.ensure_idle('owned')
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(args[0] == 'top' for args in calls))

    def test_ownership_check_precedes_process_inspection(self):
        state = self.state('PID PPID STAT\n101 0 S\n102 101 S\n')
        def reject(ident): raise ValueError('unowned')
        state.owned_container = reject
        with self.assertRaisesRegex(ValueError, 'unowned'): state.ensure_idle('other')


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux subreaper required')
class LinuxDescendantTests(unittest.TestCase):
    def exercise(self, argv, timeout=.3):
        # Isolated helper process; subreaper never changes the unittest parent's policy.
        code = '''
import json,sys,time
from pathlib import Path
from types import SimpleNamespace
from process_cleanup import enable_subreaper,cleanup_children,_direct_children
from haiagent.executor import LocalExecutor
enable_subreaper()
command=json.loads(sys.argv[1]); root=Path(sys.argv[2])
result=LocalExecutor(SimpleNamespace(workspace=root,environment={}),
 SimpleNamespace(command_seconds=5,output_bytes=16000)).execute(command,time.monotonic()+5)
cleanup=cleanup_children()
print(json.dumps({'timed_out':result.timed_out,'exit_code':result.exit_code,
 'cleanup':cleanup,'remaining_children':_direct_children()}))
'''
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ)
            for name in list(env):
                if any(s in name.upper() for s in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
                    env.pop(name)
            env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'integration'), str(ROOT/'sources/hai-project/src')])
            proc = subprocess.run([sys.executable, '-B', '-c', code,
                json.dumps(dict(argv=argv,cwd='.',timeout_seconds=timeout)),temp],
                capture_output=True,text=True,env=env,timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)

    def test_sets_id_escape_after_timeout_is_cleaned(self):
        script = ('import subprocess,sys,time; '
                  'subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"], '
                  'start_new_session=True); time.sleep(60)')
        result = self.exercise([sys.executable,'-c',script])
        self.assertTrue(result['timed_out'])
        self.assertGreaterEqual(result['cleanup']['killed'],1)
        self.assertEqual(result['remaining_children'],[])

    def test_nested_gnu_timeout_pipeline_is_cleaned(self):
        result = self.exercise(['bash','-lc','timeout 30 sleep 60 | tail -1'])
        self.assertTrue(result['timed_out'])
        self.assertGreaterEqual(result['cleanup']['killed'],1)
        self.assertEqual(result['remaining_children'],[])

    def test_successful_launcher_cannot_leave_background_child(self):
        result = self.exercise([sys.executable,'-c',
            'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True)'])
        self.assertFalse(result['timed_out'])
        self.assertGreaterEqual(result['cleanup']['killed'],1)
        self.assertEqual(result['remaining_children'],[])

    def test_clean_command_needs_no_kill(self):
        result = self.exercise([sys.executable,'-c','print("clean")'])
        self.assertEqual(result['cleanup']['killed'],0)
        self.assertEqual(result['exit_code'],0)

    def test_unrelated_parent_owned_process_is_not_killed(self):
        guard = subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
        try:
            self.test_sets_id_escape_after_timeout_is_cleaned()
            self.assertIsNone(guard.poll())
        finally:
            guard.terminate(); guard.wait(timeout=5)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux supervisor requires fcntl')
class SharedFaultTests(unittest.TestCase):
    def test_real_scheduler_loop_stops_admission_without_replay_or_api(self):
        from supervisor import Supervisor, write, read
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            instance=Supervisor.__new__(Supervisor)
            instance.root, instance.kind=root,'college'
            instance.ledger=root/'ledger'; instance.ledger.mkdir()
            instance.cache={}; instance.children=[]; instance.prior=[]
            instance.wanted=[('first',{}),('second',{}),('pending',{})]
            instance.slots=4; instance.total=3; instance.stage='screen'
            instance.supervisor_sha256='offline'; instance.disk_guard_enabled=False
            instance.ready={}; instance.event=lambda *a,**k:None
            instance.disk_ok=lambda:(True,{'fixture':100})
            for name in ('first','second'):
                report=root/name/'trial/result.json'
                agent=report.parent/'agent'; (agent/'method').mkdir(parents=True)
                end=dict(event='method_end',result={'stop_reason':'model_or_protocol_error_limit'})
                (agent/'audit.jsonl').write_text(json.dumps(end)+'\n')
                (agent/'method/events.jsonl').write_text(json.dumps(dict(event='protocol_error',
                    error_code='memory_review_too_long',field='strategy_adjustment',
                    protocol_error='strategy_adjustment: too_long'))+'\n')
                folder=instance.ledger/name; folder.mkdir()
                write(folder/'result.json',dict(method='evidence1',task=name,report=str(report),
                    classification={'reasons':[],'method_issues':['model_or_protocol_limit']}))
            with patch.dict(os.environ,{},clear=False), patch('supervisor.subprocess.Popen') as launch:
                instance.scheduler('offline-mock-not-a-real-key')
                launch.assert_not_called()
            health=read(root/'health.json')
            self.assertEqual(health['state'],'needs_attention')
            self.assertEqual(health['pending'],1)
            self.assertEqual(health['completed'],2)
            self.assertEqual(health['problems'][0]['reason'],'two_consecutive_shared_format_failures')
            self.assertFalse((instance.ledger/'pending').exists())

    def test_format_category_distinguishes_policy_refusal_from_format(self):
        from supervisor import terminal_format_category
        for message, expected in [
            ('memory_review.applicability: too_long', 'memory_review_format'),
            ('strategy_adjustment must state a concrete change/recheck and its verification', 'memory_review_format'),
            ('contrastive rejection: final_command must exactly render the executed argv; no proof/action mismatch', 'contrastive_contract_format'),
            ('contrastive rejection: unchanged_failed_executable_without_relevant_change', None),
            ('contrastive rejection: command_similarity_above_threshold', None)]:
            with self.subTest(message=message):
                self.assertEqual(terminal_format_category([dict(event='protocol_error',protocol_error=message)],
                    'model_or_protocol_error_limit'), expected)

    def test_two_shared_format_failures_pause_new_dispatch(self):
        from supervisor import shared_format_blockers
        rows = [dict(method=method,task='task'+str(i),terminal_format_category='memory_review_format')
                for i,method in enumerate(('evidence1','orthogonal1'))]
        blockers = shared_format_blockers(rows)
        self.assertEqual(blockers[0]['reason'],'two_consecutive_shared_format_failures')
        self.assertEqual(len(blockers[0]['jobs']),2)

    def test_healthy_or_different_fault_resets_streak(self):
        from supervisor import shared_format_blockers
        bad = dict(terminal_format_category='memory_review_format')
        self.assertEqual(shared_format_blockers([bad, dict(terminal_format_category=None)]), [])
        self.assertEqual(shared_format_blockers([bad, dict(terminal_format_category='contrastive_contract_format')]), [])

    def test_scientific_low_score_and_budget_do_not_trigger(self):
        from supervisor import terminal_format_category
        events=[dict(event='protocol_error',protocol_error='memory_review.applicability: too_long')]
        for stop in ('model_submit','request_or_tool_budget','wall_budget'):
            self.assertIsNone(terminal_format_category(events,stop))


if __name__ == '__main__': unittest.main()
