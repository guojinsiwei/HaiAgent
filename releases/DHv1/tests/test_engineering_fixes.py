"""DHv1 audit-defect regressions; no credentials, model calls or Docker."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.command_io import align_timeout, snapshot_logs, recover_logs
from bestfgs.delivery_safety import BootDeliveryGuard, boot_dispatch
from bestfgs.lean_cli import build_parser, config_from_args, exit_status
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_memory import action_key
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import CommandSpec, CommandResult
from test_lean import run_action


class DeliveryRegressionTests(unittest.TestCase):
    def seed(self, root, subdirectory=True):
        folder = Path(root)/'cow' if subdirectory else Path(root)
        (folder/'user').mkdir(parents=True)
        (folder/'kernel').mkdir()
        (folder/'Makefile').write_text('fixture')
        (folder/'kernel/proc.c').write_text('implementation')
        init = folder/'user/init.c'
        init.write_text('void boot(){exec("sh", argv);}')
        return init

    def check_variant(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp)
            guard = BootDeliveryGuard(tmp)
            init.write_text(content)
            report = guard.check()
            self.assertFalse(report['passed'])
            self.assertFalse(report['automatic_revert'])
            self.assertEqual(init.read_text(), content)
            return report

    def test_commented_shell_does_not_mask_test_boot(self):
        self.check_variant('// exec("sh", argv);\nvoid boot(){exec("pgtbltest", argv);}')

    def test_shell_and_extra_test_dispatch_are_not_allowed(self):
        self.check_variant('void boot(){exec("pgtbltest", argv);exec("sh", argv);}')

    def test_removed_dispatch_fails(self):
        self.check_variant('void boot(){return;}')

    def test_variable_dispatch_stays_unverified(self):
        report = self.check_variant('void boot(){char *cmd="pgtbltest";exec(cmd, argv);}')
        self.assertIn('boot_dispatch_unverified', [row['reason'] for row in report['issues']])

    def test_unknown_extra_dispatch_cannot_hide_behind_literal_shell(self):
        self.check_variant('void boot(){exec(test_name, argv);exec("sh", argv);}')

    def test_string_content_is_not_executable_code(self):
        self.check_variant(r'void boot(){printf("exec(\"sh\", argv)");exec("pgtbltest", argv);}')

    def test_spliced_line_comment_remains_comment(self):
        report = boot_dispatch('// comment \\\nexec("sh", argv);\nexec("test", argv);')
        self.assertEqual(report['programs'], ['test'])

    def test_c_escaped_and_concatenated_literal(self):
        self.assertEqual(boot_dispatch(r'exec("s" "\x68", argv);')['programs'], ['sh'])

    def test_root_xv6_workspace_is_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp, subdirectory=False)
            guard = BootDeliveryGuard(tmp)
            self.assertEqual(list(guard.baselines), ['user/init.c'])
            init.write_text('exec("pgtbltest", argv);')
            self.assertFalse(guard.check()['passed'])

    def test_unrelated_implementation_and_formatting_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp); guard = BootDeliveryGuard(tmp)
            init.write_text('/* exec("test", argv); */\nvoid boot(){ exec ( "sh" , argv ); }')
            (Path(tmp)/'cow/kernel/proc.c').write_text('new implementation')
            self.assertTrue(guard.check()['passed'])

    def test_missing_source_fails_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = self.seed(tmp); guard = BootDeliveryGuard(tmp)
            init.unlink()
            self.assertFalse(guard.check()['passed'])


class ActionAndLaunchTests(unittest.TestCase):
    def args(self, *extra):
        return build_parser().parse_args(['--workspace','seed','--run-root','run',
                                         '--goal','fixture','--model','fixture-model', *extra])

    def test_expectation_change_is_not_executable_change(self):
        original = run_action('cat', 'config.txt', expected_observation={'kind':'output','contains':'v1'})
        revised = dict(original, expected_observation={'kind':'output','contains':'v2'})
        self.assertEqual(action_key(original), action_key(revised))
        self.assertEqual(LeanTaskRunner._action_core(original), LeanTaskRunner._action_core(revised))

    def test_actual_command_change_still_counts(self):
        original = run_action('cat','config.txt')
        revised = run_action('cat','other.txt')
        self.assertNotEqual(LeanTaskRunner._action_core(original), LeanTaskRunner._action_core(revised))

    def test_default_configuration_is_dh_not_hai(self):
        config = config_from_args(self.args())
        self.assertEqual(config.contrastive_mode, 'orthogonal')
        self.assertFalse(config.route_search)
        self.assertFalse(config.stagnation_control)
        self.assertFalse(config.contrastive_predictions)
        self.assertTrue(config.expectation_enabled)
        self.assertTrue(config.memory_reliability)
        self.assertTrue(config.outcome_reliability)
        self.assertEqual((config.max_turns,config.max_tools,config.wall_seconds,config.command_seconds),
                         (800,600,3600,300))

    def test_hai_flags_are_rejected(self):
        for flag in ('--route-search','--stagnation-control'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                config_from_args(self.args(flag))

    def test_invalid_required_reliability_is_rejected_before_model_creation(self):
        for flag in ('--no-memory-reliability','--no-outcome-reliability'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                config_from_args(self.args(flag))

    def test_partial_budget_artifact_is_not_a_process_failure(self):
        self.assertEqual(exit_status({'artifact':{'path':'fixture'},'stop_reason':'budget_exhausted'}),0)

    def test_invalid_deliveries_and_protocol_stops_are_nonzero(self):
        results = [{}, {'artifact':{},'error_type':'ValueError'},
                   {'artifact':{'delivery_preflight':{'passed':False}}},
                   {'artifact':{'path':'fixture'},'stop_reason':'delivery_guard_failed'},
                   {'artifact':{'path':'fixture'},'stop_reason':'model_or_protocol_error_limit'}]
        for result in results:
            with self.subTest(result=result):
                self.assertEqual(exit_status(result),1)


class TimeoutBackendTests(unittest.TestCase):
    def test_direct_argv_clock_alignment(self):
        for argv in [('timeout','90','make','qemu'),
                     ('/usr/bin/timeout','1.5m','qemu-system-riscv64')]:
            action = run_action(*argv)
            repaired, note = align_timeout(action,300)
            self.assertEqual(repaired['timeout_seconds'],100)
            self.assertNotIn('timeout_seconds',action)
            self.assertTrue(note['task_deadline_unchanged'])

    def test_direct_argv_alignment_does_not_expand_cap(self):
        repaired, note = align_timeout(run_action('timeout','10m','make','qemu'),300)
        self.assertEqual(repaired['timeout_seconds'],300)
        self.assertTrue(note['inner_limit_exceeds_cap'])

    def test_non_qemu_direct_argv_is_unchanged(self):
        repaired, _ = align_timeout(run_action('timeout','90','python','test.py'),300)
        self.assertEqual(repaired['timeout_seconds'],60)

    def test_workspace_mapping_freshness_and_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'cow').mkdir()
            path = root/'cow/qout.txt'; path.write_text('old')
            action = run_action('bash','-lc','cd cow && make qemu > qout.txt')
            before = snapshot_logs(action, workspace_root=root)
            self.assertEqual(recover_logs(action, before=before, workspace_root=root),[])
            path.write_bytes(b'x'*1000)
            rows = recover_logs(action, before=before, workspace_root=root, byte_limit=100)
            self.assertEqual(rows[0]['path'],'/app/cow/qout.txt')
            self.assertEqual(rows[0]['captured_bytes'],100)
            self.assertTrue(rows[0]['partial'])
            self.assertIsNone(rows[0]['task_success'])

    def test_live_backend_does_not_read_shared_host_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            action = run_action('bash','-lc','make qemu > /tmp/qout.txt')
            self.assertEqual(snapshot_logs(action, workspace_root=tmp),{})
            self.assertEqual(recover_logs(action, workspace_root=tmp),[])

    def test_live_backend_timeout_recovery_keeps_failure_on_both_paths(self):
        for traced in (False, True):
            with self.subTest(traced=traced), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                env = object.__new__(LiveWorkspace)
                env.workspace = root; env.outcome_reliability = traced
                action = run_action('bash','-lc','make qemu > qout.txt')
                def execute(action, deadline):
                    (root/'qout.txt').write_text('PARTIAL LOG NOT A PASS')
                    return CommandResult(CommandSpec(tuple(action['argv']), 'fixture'),124,'','',0.1,timed_out=True)
                with patch.object(env,'_execute',side_effect=execute), \
                     patch('bestfgs.lean_environment.prepare_trace',return_value=(action,object())), \
                     patch('bestfgs.lean_environment.finish_trace',return_value={'fixture':True}):
                    result = env.execute(action,time.monotonic()+10)
                self.assertTrue(result.timed_out)
                self.assertEqual(result.return_code,124)
                self.assertIn('PARTIAL LOG NOT A PASS', result.stdout)
                self.assertIsNone(result.execution_observation['recovered_logs'][0]['task_success'])
                if traced:
                    self.assertTrue(result.execution_observation['fixture'])

    @unittest.skipUnless(os.name == 'posix','requires real Linux process groups')
    def test_real_live_timeout_recovers_workspace_log_without_false_pass(self):
        for traced in (False,True):
            with self.subTest(traced=traced), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); seed = root/'seed'; seed.mkdir()
                env = LiveWorkspace(seed,root/'run')
                env.outcome_reliability = traced
                action = run_action('bash','-lc',
                    "printf 'qemu fixture partial log' > qout.txt; sleep 10",timeout_seconds=0.5)
                result = env.execute(action,time.monotonic()+5)
                self.assertTrue(result.timed_out)
                self.assertNotEqual(result.return_code,0)
                self.assertLess(result.duration_seconds,5)
                self.assertIn('qemu fixture partial log',result.stdout)
                self.assertIsNone(result.execution_observation['recovered_logs'][0]['task_success'])


if __name__ == '__main__':
    unittest.main()
