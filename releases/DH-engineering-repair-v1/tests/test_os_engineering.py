"""Offline regressions from the OS logs: no keys, APIs or Docker required."""
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests'), str(ROOT/'compatibility/src'),
               str(ROOT/'harness')]
from bestfgs.command_io import align_timeout, recover_logs, snapshot_logs, redirected_logs
from bestfgs.delivery_safety import BootDeliveryGuard
from bestfgs.memory_events import dependency_paths
from bestfgs.contrastive_exploration import ContrastiveExploration, command_text
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


class PathTests(unittest.TestCase):
    def test_leading_cd_resolves_real_kernel_path(self):
        paths = dependency_paths(run_action('bash', '-lc', 'cd cow && cat kernel/vm.c fs.img'))
        self.assertIn('cow/kernel/vm.c', paths)
        self.assertIn('cow/fs.img', paths)
        self.assertNotIn('kernel/vm.c', paths)

    def test_explicit_cwd_and_absolute_paths_are_not_double_prefixed(self):
        paths = dependency_paths(run_action('cat', 'kernel/vm.c', '/app/cow/fs.img', cwd='/app/cow'))
        self.assertEqual(paths, ['cow/kernel/vm.c', 'cow/fs.img'])

    def test_quoted_cd_and_known_paths(self):
        paths = dependency_paths(run_action('bash', '-lc', "cd 'cow' && cat kernel/vm.c"), ['notes.txt'])
        self.assertEqual(paths, ['cow/kernel/vm.c', 'notes.txt'])

    def test_ambiguous_shell_does_not_guess_relative_targets(self):
        for script in ['cd "$DIR" && cat kernel/vm.c /app/cow/README',
                       'cd cow || cd net; cat kernel/vm.c /app/cow/README',
                       '(cd cow && cat kernel/vm.c); cat /app/cow/README',
                       'cd cow; cat kernel/vm.c /app/cow/README']:
            paths = dependency_paths(run_action('bash', '-lc', script))
            self.assertNotIn('kernel/vm.c', paths)
            self.assertNotIn('cow/kernel/vm.c', paths)
            self.assertIn('cow/README', paths)

    def test_external_and_traversal_targets_not_observed(self):
        paths = dependency_paths(run_action('cat', '/etc/passwd', '../../secret.txt'))
        self.assertEqual(paths, [])

    def test_correct_path_reaches_diagnostic_script(self):
        class Gate(ContrastiveExploration):
            def _emit(self, *args, **kwargs): pass
            _action_core = staticmethod(LeanTaskRunner._action_core)
        g = Gate(); g.config = LeanConfig(contrastive_mode='orthogonal',
            contrastive_predictions=False, memory_reliability=True, outcome_reliability=True)
        g.environment = FakeEnvironment(); g.counts = Counter(); g._init_contrastive()
        g.contrastive_episode = dict(id='X1', phase='plan')
        g.contrastive_visible_anchors = [dict(dependencies={'cow/kernel/kernel': 'missing'})]
        action = run_action('cat', 'cow/kernel/vm.c')
        first = g._contrastive_before(action)
        self.assertEqual(first['rejection_class'], 'proposal_schema')
        self.assertIn('orthogonality_proof', first['schema_repair']['required_keys'])
        second = g._contrastive_before(action)
        self.assertIn('cow/kernel/kernel', second['fallback_action']['argv'][2])
        self.assertEqual(g.counts['contrastive_rejections'], 2)


class CommandIOTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'requires real POSIX process-group termination')
    def test_real_process_timeout_keeps_partial_log_and_failure(self):
        from haiagent.executor import LocalExecutor
        from haiagent.protocol import Config, Task
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); workspace = root/'app'; workspace.mkdir()
            executor = LocalExecutor(Task('fixture', 'Offline timeout fixture', workspace),
                                     Config(method='raw', command_seconds=2))
            action = run_action('bash', '-lc',
                "printf 'qemu fixture: partial, not a pass' > qout.txt; sleep 10",
                timeout_seconds=0.5, cwd='.')
            before = snapshot_logs(action, root)
            result = executor.execute(action, time.monotonic()+5)
            self.assertTrue(result.timed_out)
            self.assertNotEqual(result.exit_code, 0)
            self.assertLess(result.duration_seconds, 5)
            rows = recover_logs(action, root, before=before)
            self.assertEqual(rows[0]['text'], 'qemu fixture: partial, not a pass')
            self.assertIsNone(rows[0]['task_success'])

    @unittest.skipUnless(os.name == 'posix', 'symlink creation is permission-dependent on Windows')
    def test_recovery_rejects_parent_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp); (root/'app').mkdir()
            (Path(outside)/'secret.txt').write_text('must not be recovered')
            (root/'app/logs').symlink_to(outside, target_is_directory=True)
            action = run_action('bash', '-lc', 'make qemu > logs/secret.txt')
            self.assertEqual(recover_logs(action, root), [])

    def test_shared_executor_preserves_timeout_and_exposes_recovered_log(self):
        from environment import SandboxExecutor, LocalExecutor, Result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'app').mkdir(); (root/'tmp').mkdir()
            executor = SandboxExecutor(root)
            def timeout_result(command, deadline):
                (root/'tmp/qout').write_text('kernel booted; test outcome unknown')
                return Result(-9, timed_out=True)
            action = run_action('bash', '-lc', 'timeout 90 make qemu > /tmp/qout; cat /tmp/qout')
            with patch.object(LocalExecutor, 'execute', side_effect=timeout_result):
                result = executor.execute(action, time.monotonic()+300)
            self.assertTrue(result.timed_out)
            self.assertEqual(result.exit_code, -9)
            self.assertIn('test outcome unknown', result.stdout)
            self.assertIsNone(result.recovered_logs[0]['task_success'])
            self.assertEqual(result.command_clock['effective_seconds'], 100)

    def test_outer_clock_covers_inner_qemu_and_collection(self):
        action = run_action('bash', '-lc', 'cd pgtbl && timeout 90 make qemu > /tmp/qout; cat /tmp/qout',
                            timeout_seconds=60)
        repaired, note = align_timeout(action, 300)
        self.assertEqual(repaired['timeout_seconds'], 100)
        self.assertEqual(action['timeout_seconds'], 60)
        self.assertTrue(note['task_deadline_unchanged'])

    def test_never_enlarges_command_cap(self):
        repaired, note = align_timeout(run_action('bash', '-lc', 'timeout 600 make qemu'), 300)
        self.assertEqual(repaired['timeout_seconds'], 300)
        self.assertTrue(note['inner_limit_exceeds_cap'])

    def test_non_qemu_timeout_unchanged(self):
        repaired, _ = align_timeout(run_action('bash', '-lc', 'timeout 90 python check.py'), 300)
        self.assertEqual(repaired['timeout_seconds'], 60)

    def test_relative_redirect_in_cd_has_correct_path(self):
        self.assertEqual(redirected_logs(run_action('bash', '-lc',
            'cd cow && timeout 90 make qemu > qout.txt 2>&1; cat qout.txt')), ['/app/cow/qout.txt'])

    def test_timeout_recovers_new_log_but_not_stale_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'tmp').mkdir(); path = root/'tmp/qout'
            path.write_text('OLD RESULT')
            action = run_action('bash', '-lc', 'timeout 90 make qemu > /tmp/qout 2>&1; cat /tmp/qout')
            before = snapshot_logs(action, root)
            self.assertEqual(recover_logs(action, root, before=before), [])
            path.write_text('PARTIAL BOOT RESULT, NOT A PASS')
            rows = recover_logs(action, root, before=before)
            self.assertEqual(rows[0]['text'], 'PARTIAL BOOT RESULT, NOT A PASS')
            self.assertIsNone(rows[0]['task_success'])

    def test_recovery_is_bounded_and_marks_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'tmp').mkdir(); (root/'tmp/qout').write_bytes(b'x'*5000)
            action = run_action('bash', '-lc', 'timeout 90 make qemu > /tmp/qout')
            rows = recover_logs(action, root, byte_limit=100)
            self.assertEqual(rows[0]['captured_bytes'], 100)
            self.assertTrue(rows[0]['partial'])

    def test_recovery_rejects_outside_workspace_and_dynamic_targets(self):
        for name in ['/etc/passwd', '/tmp/../../secret', '$OUT']:
            self.assertEqual(redirected_logs(run_action('bash', '-lc', 'make qemu > '+name)), [])


class DeliveryTests(unittest.TestCase):
    def seed(self, root):
        root = Path(root); (root/'pgtbl/user').mkdir(parents=True); (root/'pgtbl/kernel').mkdir()
        (root/'pgtbl/Makefile').write_text('fixture')
        (root/'pgtbl/kernel/proc.c').write_text('fixture')
        (root/'pgtbl/user/pgtbltest.c').write_text('fixture')
        init = root/'pgtbl/user/init.c'
        init.write_text('char *argv[] = {"sh", 0}; void boot(){exec("sh", argv);}')
        return init

    def test_boot_test_substitution_detected_without_reverting(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp); guard = BootDeliveryGuard(tmp)
            changed = 'char *argv[] = {"pgtbltest", 0}; void boot(){exec("pgtbltest", argv);}'
            init.write_text(changed)
            report = guard.check()
            self.assertFalse(report['passed'])
            self.assertEqual(report['issues'][0]['path'], 'pgtbl/user/init.c')
            self.assertEqual(init.read_text(), changed)
            self.assertFalse(report['automatic_revert'])

    def test_restoration_clears_guard_and_legitimate_other_edits_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp); guard = BootDeliveryGuard(tmp)
            init.write_text(init.read_text()+'\n// legitimate logging change')
            self.assertTrue(guard.check()['passed'])
            (Path(tmp)/'pgtbl/kernel/proc.c').write_text('real implementation')
            self.assertTrue(guard.check()['passed'])

    def test_non_os_workspace_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(BootDeliveryGuard(tmp).check()['passed'])

    def test_runtime_submit_guard_feedback_and_budget_exit(self):
        class Guarded(FakeEnvironment):
            def delivery_preflight(self):
                return dict(passed=self.value=='fixed', issues=['temporary boot mutation'], task_success=None)
            def delivery(self):
                return dict(super().delivery(), delivery_preflight=self.delivery_preflight())
        for actions, expected in [([SUBMIT, run_action('write','fixed'), SUBMIT], True), ([SUBMIT], False)]:
            with tempfile.TemporaryDirectory() as tmp:
                env = Guarded(); actor = Scripted(actions)
                runner = LeanTaskRunner(env, actor, Scripted([]),
                    LeanConfig(max_turns=len(actions), max_tools=10), Path(tmp)/'trace')
                result = runner.run(TaskSpec('fixture', 'Implement the public task'))
                self.assertEqual(result['submitted'], expected, result)
                if not expected:
                    self.assertEqual(result['stop_reason'], 'delivery_guard_failed')
                events = read_trace(Path(tmp)/'trace/events.jsonl')
                self.assertTrue(any(e['event']=='submission_preflight_rejected' for e in events))

    def test_raw_uses_same_public_delivery_guard_without_memory(self):
        from haiagent.runtime import run
        from haiagent.protocol import Config, Task
        from haiagent.demo import ScriptedClient
        from haiagent.executor import Result
        class Executor:
            good = False
            def execute(self, command, deadline):
                self.good = True
                return Result(0, stdout='boot shell restored')
            def delivery_preflight(self):
                return dict(passed=self.good, issues=[] if self.good else ['test replaced boot shell'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); workspace = root/'app'; workspace.mkdir()
            client = ScriptedClient([SUBMIT, run_action('fixture-restore'), SUBMIT])
            result = run(Task('fixture', 'Public task', workspace, delivery='terminal'),
                         Config(method='raw', response_protocol='json', max_turns=3, max_tools=2),
                         client, root/'trace', executor=Executor())
            self.assertTrue(result['submitted'], result)
            self.assertEqual(result['interaction_rounds'], 3)
            self.assertEqual(result['tool_calls'], 1)
            self.assertTrue(result['delivery_preflight']['passed'])


if __name__ == '__main__':
    unittest.main()
