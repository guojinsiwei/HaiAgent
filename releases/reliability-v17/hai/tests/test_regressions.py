"""Integration failures found after the first delivery; offline, no provider calls."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from haiagent.demo import ScriptedClient
from haiagent.executor import Result, LocalExecutor, workspace_revision
from haiagent.metrics import load_run, attach_evaluation, summarize_run
from haiagent.cli import main, run_exit_code
from haiagent.file_evidence import FileEvidenceTracker
from haiagent.evaluation import source_success
from haiagent.model import ModelError
from haiagent.storage import atomic_json
from haiagent.protocol import Config, Task
from haiagent.runtime import build_messages, record_pair, run
from terminal_context import TaskContext, TerminalEvent, MemoryCandidate


class IntegrationRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = self.root / 'workspace'
        self.ws.mkdir()
        self.task = Task('T1', 'inspect error and config.py', self.ws, delivery='terminal')

    def test_unknown_environment_retains_repeated_failure_as_history(self):
        class Failed:
            def execute(self, *args):
                return Result(1, stderr='ModuleNotFoundError: missing package')
        client = ScriptedClient([{'action': 'run', 'argv': ['python', 'app.py']}] * 2
                                + [{'action': 'submit', 'summary': 'done'}])
        run(self.task, Config(), client, self.root / 'run', executor=Failed())
        memory = json.loads(client.requests[2][1]['content'])['context']['task_memory']
        self.assertTrue(memory)
        self.assertEqual(memory[0]['validity'], 'unknown')
        self.assertEqual(memory[0]['use_mode'], 'historical_reference')

    def test_raw_never_silently_drops_latest_feedback(self):
        cfg = Config(method='raw')
        task = replace(self.task, instruction='task ' * 4000)
        history = []
        record_pair(history, {'action': 'run', 'argv': ['python'], 'stdin': 'x' * 14000},
                    {'id': 'E1', 'stdout': 'a' * 8000, 'stderr': 'b' * 8000, 'exit_code': 1}, 1, cfg)
        messages, ids, _ = build_messages(task, cfg, None, history, None, {})
        self.assertIn(1, ids)
        self.assertTrue(any('"id":"E1"' in m['content'] for m in messages))
        self.assertLessEqual(len(json.dumps(messages, ensure_ascii=False, sort_keys=True,
                                           separators=(',', ':')).encode()), cfg.prompt_bytes)

    def test_terminal_artifact_tamper_rejected(self):
        out = self.root / 'run'
        run(self.task, Config(), ScriptedClient([{'action': 'submit', 'summary': 'done'}]), out)
        (out / 'terminal-submission.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_run(out)

    def test_unknown_recovery_retained_without_causal_claim(self):
        ctx = TaskContext('T', 'python app.py')
        ctx.observe(TerminalEvent('T', 'python app.py', stderr='RuntimeError: failed', exit_code=1))
        ctx.observe(TerminalEvent('T', 'python app.py', stdout='ok', exit_code=0))
        self.assertEqual(ctx.snapshot()['memories'][0]['kind'], 'recovery')
        self.assertEqual(ctx.recall(), [])  # unknown is never certified as currently applicable

    def test_subdirectory_evidence_can_be_retained_as_history(self):
        ctx = TaskContext('T', 'config.py')
        ctx.observe(TerminalEvent('T', 'cat config.py', stdout='setting=1', exit_code=0,
                                  cwd='/repo/pkg', workspace='w'))
        ctx.set_scope(cwd='/repo', workspace='w')
        mid = ctx.remember(MemoryCandidate('config.py setting=1', 'inspect config.py', ('E1',),
                                          dependencies=('workspace',)), allow_historical=True)
        self.assertIsNotNone(mid)
        self.assertEqual(ctx.snapshot()['memories'][0]['scope']['cwd'], '/repo/pkg')

    def test_file_finding_survives_unrelated_log_not_source_edit(self):
        pkg = self.ws / 'pkg'
        pkg.mkdir()
        source = pkg / 'config.py'
        source.write_text('setting=1')
        tracker = FileEvidenceTracker(self.ws)
        tracker.select({'argv': ['cat', 'config.py'], 'cwd': 'pkg'})
        files = tracker.refresh(time.monotonic() + 10)
        ctx = TaskContext('T', 'config.py')
        ctx.observe(TerminalEvent('T', 'cat config.py', stdout='setting=1', exit_code=0,
                    cwd=str(pkg), workspace=None, file_revisions=files))
        ctx.set_scope(cwd=str(self.ws), workspace=None, file_revisions=files)
        ctx.remember(MemoryCandidate('config.py setting=1', 'inspect config.py', ('E1',),
                                    dependencies=('workspace',)), allow_historical=True)
        (self.ws / 'log.txt').write_text('unrelated')
        ctx.set_scope(cwd=str(self.ws), file_revisions=tracker.refresh(time.monotonic() + 10))
        self.assertEqual(ctx.recall('config.py')[0]['validity'], 'current')
        source.write_text('setting=2')
        ctx.set_scope(cwd=str(self.ws), file_revisions=tracker.refresh(time.monotonic() + 10))
        self.assertEqual(ctx.recall('config.py'), [])
        self.assertEqual(ctx.recall('config.py', include_historical=True)[0]['validity'], 'stale')

    def test_file_tracking_bounded_and_shell_not_misinterpreted(self):
        tracker = FileEvidenceTracker(self.ws)
        self.assertEqual(tracker.select({'argv': ['bash', '-c', 'cat file'], 'cwd': '.'}), [])
        self.assertEqual(tracker.select({'argv': ['cat', '../outside'], 'cwd': '.'}), [])
        for i in range(50):
            tracker.select({'argv': ['cat', str(i)], 'cwd': '.'})
        self.assertEqual(len(tracker.paths), 32)

    def test_background_launcher_not_killed_for_inherited_output(self):
        child = 'import time,pathlib;time.sleep(1);pathlib.Path("alive").write_text("yes")'
        parent = ('import subprocess,sys,pathlib;p=subprocess.Popen([sys.executable,"-c",' + repr(child)
                  + ']);pathlib.Path("child.pid").write_text(str(p.pid))')
        command = {'argv': [sys.executable, '-c', parent], 'cwd': '.', 'timeout_seconds': 3}
        import haiagent.executor as module
        with patch.object(module, 'stop_tree', wraps=module.stop_tree) as terminate:
            result = LocalExecutor(self.task, Config()).execute(command, time.monotonic() + 4)
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.background_output_open)
            terminate.assert_not_called()
        until = time.monotonic() + 3
        while not (self.ws / 'alive').exists() and time.monotonic() < until:
            time.sleep(0.05)
        self.assertTrue((self.ws / 'alive').exists())
        # A written marker proves liveness, not process exit. In Windows the child
        # still owns cwd for a moment; wait for the actual process before cleanup.
        pid = int((self.ws / 'child.pid').read_text())
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 3000), 0)
                finally:
                    kernel.CloseHandle(handle)
            else:
                self.assertEqual(ctypes.get_last_error(), 87)  # already exited

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO test needs Linux/macOS')
    def test_fifo_never_opened_as_regular_workspace_file(self):
        os.mkfifo(self.ws / 'pipe')
        self.assertIsNone(workspace_revision(self.ws))

    def test_exit_codes_distinguish_submission_budget_and_faults(self):
        for reason, code in [('model_submit', 0), ('api_error', 4), ('infrastructure_error', 5),
                             ('wall_budget', 3), ('context_budget', 3), ('interrupted', 130)]:
            self.assertEqual(run_exit_code({'submitted': reason == 'model_submit', 'stop_reason': reason}), code)

    def test_cli_returns_nonzero_on_provider_failure(self):
        class FailedProvider:
            def complete(self, *args):
                raise ModelError('provider rejected request')
        atomic_json(self.root / 'task.json', {'task_id': 'T1', 'instruction': 'inspect',
                                            'workspace': 'workspace', 'delivery': 'terminal'})
        atomic_json(self.root / 'config.json', {'api': {'base_url': 'https://unused.invalid', 'model': 'offline'}})
        with patch('haiagent.cli.APIClient', return_value=FailedProvider()), patch('builtins.print'):
            code = main(['run', '--task', str(self.root / 'task.json'), '--config', str(self.root / 'config.json'),
                         '--out', str(self.root / 'run'), '--allow-local-execution'])
        self.assertEqual(code, 4)
        self.assertEqual(load_run(self.root / 'run')[0]['stop_reason'], 'api_error')

    def test_source_reports_fail_closed(self):
        self.assertFalse(source_success({'T1': {'resolved': False}}, 'T1', 'swe-instance-v1'))
        self.assertTrue(source_success({'resolved_ids': ['T1'], 'unresolved_ids': []}, 'T1', 'swe-summary-v1'))
        for report, fmt in [({'T2': {'resolved': True}}, 'swe-instance-v1'),
                            ({'T1': {'resolved': False, 'infra_failure': True}}, 'swe-instance-v1'),
                            ({'resolved_ids': ['T1'], 'unresolved_ids': ['T1']}, 'swe-summary-v1'),
                            ({'reward': 0}, 'fixture-reward-v1'), ({'reward': 1}, 'invented')]:
            with self.assertRaises(ValueError):
                source_success(report, 'T1', fmt)

    def test_false_normalized_success_rejected_and_report_portable(self):
        import hashlib
        import shutil
        out = self.root / 'run'
        result = run(self.task, Config(), ScriptedClient([{'action': 'submit', 'summary': 'done'}]), out)
        source = self.root / 'official.json'
        atomic_json(source, {'T1': {'resolved': False}})
        report = {'schema': 'hai-external-evaluation-v1', 'run_id': result['run_id'], 'task_id': 'T1',
                  'artifact_sha256': result['artifact']['sha256'], 'success': True, 'independent': True,
                  'evaluator': 'offline-fixture', 'source_format': 'swe-instance-v1', 'source_report': 'official.json',
                  'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        path = self.root / 'normalized.json'
        atomic_json(path, report)
        with self.assertRaises(ValueError):
            attach_evaluation(out, path)
        report['success'] = False
        atomic_json(path, report)
        attach_evaluation(out, path)
        moved = self.root / 'copied-run'
        shutil.copytree(out, moved)
        source.unlink()
        self.assertIs(summarize_run(moved)['success'], False)

    def test_latest_feedback_not_duplicated_in_context(self):
        class Reader:
            def execute(self, *args):
                return Result(0, stdout='unique-observation-marker')
        client = ScriptedClient([{'action': 'run', 'argv': ['cat', 'config.py']},
                                 {'action': 'submit', 'summary': 'done'}])
        run(self.task, Config(), client, self.root / 'run', executor=Reader())
        self.assertEqual(json.dumps(client.requests[1]).count('unique-observation-marker'), 1)

    def test_modified_patch_rejected_by_summary(self):
        from haiagent.demo import demo
        out = self.root / 'demo'
        demo(out)
        # demo stores its run in a child directory; resolve from actual output files.
        result_path = next(out.rglob('result.json'))
        directory = result_path.parent
        result, _ = load_run(directory)
        (directory / result['artifact']['path']).write_bytes(b'not the submitted patch')
        with self.assertRaises(ValueError):
            summarize_run(directory)

    def test_hai_long_feedback_stays_visible_and_bounded(self):
        ctx = TaskContext('T1', 'use the protected instruction')
        cfg = Config()
        task = replace(self.task, instruction='task ' * 4000)
        history = []
        record_pair(history, {'action': 'run', 'argv': ['python'], 'stdin': 'x' * 14000},
                    {'id': 'E1', 'stdout': 'a' * 8000, 'stderr': 'b' * 8000, 'exit_code': 1}, 1, cfg)
        messages, ids, _ = build_messages(task, cfg, ctx, history, None, {})
        self.assertIn(1, ids)
        from haiagent.runtime import message_bytes
        self.assertLessEqual(message_bytes(messages), cfg.prompt_bytes)
        self.assertIn('context', json.loads(messages[1]['content']))


if __name__ == '__main__':
    unittest.main()
