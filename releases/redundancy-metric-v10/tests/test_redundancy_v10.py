"""Offline counterexamples for the actual new detector, not just field aliases."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.experiment_metrics import ExperimentRecorder, summarize_trace
from bestfgs.models import CommandSpec, CommandResult, MacroAction
from bestfgs.redundancy import aggregate_redundancy, python_read, binary_state, file_state, LIMIT
import compare_experiments as comparison
import test_raw_comparison as fixtures


class RedundancyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / 'seed'
        self.seed.mkdir()
        (self.seed / 'a.txt').write_text('hello\n')
        (self.seed / 'other.txt').write_text('old')
        (self.seed / 'check.py').write_text("print('ok')")
        self.rec = ExperimentRecorder(self.root / 'trace.jsonl')
        self.env = ForkedWorkspaceEnvironment(self.seed, self.root / 'runs', recorder=self.rec)

    def run_command(self, argv=('cat', 'a.txt'), *, output='hello\n', code=0, phase='action',
                    mutate=None, truncated=False, blocked=False, timed_out=False, cwd='.'):
        command = CommandSpec(tuple(argv), 'description is irrelevant', cwd=cwd)
        def invoke():
            if mutate:
                mutate()
            return CommandResult(command, code, output, '', .01, blocked=blocked,
                                 timed_out=timed_out, output_truncated=truncated)
        # Linux command names are resolved to an immutable test binary on Windows.
        # Outputs are fixtures; the real common-executor integration is below.
        with patch('bestfgs.redundancy.shutil.which', return_value=sys.executable):
            with self.rec.batch(phase):
                self.rec.command(self.env, self.seed, command, invoke)
        return self.rec.summary()

    def test_unrelated_change_no_longer_hides_redundant_read(self):
        self.run_command()
        (self.seed / 'other.txt').write_text('new')
        m = self.run_command()
        self.assertEqual(m['redundant_tool_calls'], 1)
        self.assertEqual(m['mechanical_repeat_calls'], 0)
        self.assertEqual(m['tool_call_redundancy_rate'], .5)
        self.assertEqual(m['redundancy_rate_bounds'], [.5, .5])

    def test_relevant_file_changed_even_if_query_output_same_is_not_redundant(self):
        self.run_command(('head', '-n', '1', 'a.txt'))
        (self.seed / 'a.txt').write_text('hello\nextra')
        m = self.run_command(('head', '-n', '1', 'a.txt'))
        self.assertEqual(m['redundant_tool_calls'], 0)

    def test_supported_equivalent_read_and_normalized_relative_path(self):
        self.run_command(('cat', './a.txt'))
        m = self.run_command(('sed', '-n', '1,$p', 'a.txt'))
        self.assertEqual(m['redundant_tool_calls'], 1)
        self.assertEqual(m['mechanical_repeat_calls'], 0)
        end = json.loads(self.rec.path.read_text().splitlines()[-1])
        self.assertEqual(end['redundancy']['earlier_call_id'], 1)

    def test_different_slice_or_different_output_not_redundant(self):
        self.run_command(('sed', '-n', '1p', 'a.txt'))
        self.run_command(('sed', '-n', '2p', 'a.txt'))
        self.assertEqual(self.run_command(('sed', '-n', '1p', 'a.txt'), output='new')['redundant_tool_calls'], 0)

    def test_final_check_exempt_once_not_unlimited(self):
        argv = (sys.executable, 'check.py')
        self.run_command(argv, phase='functional_verification', output='ok')
        self.assertEqual(self.run_command(argv, phase='verification', output='ok')['redundant_tool_calls'], 0)
        m = self.run_command(argv, phase='verification', output='ok')
        self.assertEqual(m['redundant_tool_calls'], 1)
        self.assertEqual(m['redundancy_by_phase']['final_verification']['redundant_tool_calls'], 1)
        self.assertEqual(m['redundancy_reason_counts']['required_final_recheck'], 1)

    def test_verification_after_source_edit_is_new_evidence(self):
        argv = (sys.executable, 'check.py')
        self.run_command(argv, phase='verification')
        (self.seed / 'other.txt').write_text('new implementation')
        m = self.run_command(argv, phase='verification')
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_reason_counts']['required_final_recheck'], 2)

    def test_repeated_public_failure_without_change_can_count(self):
        argv = (sys.executable, 'check.py')
        self.run_command(argv, phase='functional_verification', code=1, output='assert 1 == 2')
        m = self.run_command(argv, phase='functional_verification', code=1, output='assert 1 == 2')
        self.assertEqual(m['redundant_tool_calls'], 1)

    def test_same_probe_same_rules_in_action_and_verification(self):
        argv = (sys.executable, 'check.py')
        self.run_command(argv, phase='action', output='ok')
        m = self.run_command(argv, phase='functional_verification', output='ok')
        self.assertEqual(m['redundant_tool_calls'], 1)

    def test_pytest_time_is_not_new_evidence_but_result_counts_are(self):
        argv = (sys.executable, '-m', 'pytest', '-q', 'check.py')
        self.run_command(argv, output='1 passed in 0.01s\n')
        m = self.run_command(argv, output='1 passed in 0.27s\n')
        self.assertEqual(m['redundant_tool_calls'], 1)
        m = self.run_command(argv, output='2 passed in 0.27s\n')
        self.assertEqual(m['redundant_tool_calls'], 1)

    def test_network_retry_is_unknown_not_redundant(self):
        for _ in range(2):
            m = self.run_command((sys.executable, 'check.py'), phase='verification', code=1, output='ConnectionError')
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_unknown_calls'], 2)

    def test_unsupported_shell_calls_are_explicitly_unknown(self):
        for _ in range(2):
            m = self.run_command(('bash', '-c', 'cat a.txt'))
        self.assertEqual(m['mechanical_repeat_calls'], 1)
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_classification_coverage'], 0)
        self.assertEqual(m['redundancy_rate_bounds'], [0, 1])

    def test_unknowns_stay_in_all_call_denominator(self):
        self.run_command()
        self.run_command()
        m = self.run_command(('curl', 'https://example.invalid'))
        self.assertEqual(m['tool_call_redundancy_rate'], 1 / 3)
        self.assertEqual(m['redundancy_rate_bounds'], [1 / 3, 2 / 3])

    def test_incomplete_output_never_seeds_reusable_evidence(self):
        self.run_command(truncated=True)
        m = self.run_command()
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_unknown_calls'], 1)

    def test_blocked_timeout_are_unknown(self):
        self.run_command(blocked=True)
        m = self.run_command(timed_out=True)
        self.assertEqual(m['redundancy_unknown_calls'], 2)
        self.assertEqual(m['redundant_tool_calls'], 0)

    def test_rg_no_match_is_complete_evidence(self):
        self.run_command(('rg', 'absent', 'a.txt'), output='', code=1)
        m = self.run_command(('rg', 'absent', 'a.txt'), output='', code=1)
        self.assertEqual(m['redundant_tool_calls'], 1)

    def test_missing_external_or_directory_dependency_is_unknown(self):
        self.run_command(('cat', 'missing'))
        self.run_command(('cat', str(self.root / 'outside')))
        m = self.run_command(('rg', 'hello', '.'))
        self.assertEqual(m['redundancy_unknown_calls'], 3)

    def test_environment_change_invalidates_evidence_and_secret_not_logged(self):
        with patch.dict(os.environ, {'METRIC_TEST_VALUE': 'secret-one'}):
            self.run_command()
        with patch.dict(os.environ, {'METRIC_TEST_VALUE': 'secret-two'}):
            m = self.run_command()
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertNotIn('secret-', self.rec.path.read_text())

    def test_state_changes_during_call_prevent_reuse(self):
        self.run_command()
        m = self.run_command(mutate=lambda: (self.seed / 'a.txt').write_text('changed'))
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_unknown_calls'], 1)

    def test_new_recorder_task_does_not_share_evidence(self):
        self.run_command()
        self.rec = ExperimentRecorder(self.root / 'other-trace.jsonl')
        self.assertEqual(self.run_command()['redundant_tool_calls'], 0)

    def test_trace_round_trip_and_broken_new_schema(self):
        self.run_command()
        expected = self.run_command()
        self.assertEqual(summarize_trace(self.rec.path), expected)
        lines = [json.loads(x) for x in self.rec.path.read_text().splitlines()]
        lines[-1].pop('redundancy')
        self.rec.path.write_text('\n'.join(map(json.dumps, lines)))
        m = summarize_trace(self.rec.path)
        self.assertFalse(m['trace_complete'])
        self.assertIsNone(m['tool_call_redundancy_rate'])

    def test_real_executor_python_read_across_forks_and_unrelated_edit(self):
        first = self.env.initial_snapshot()
        read = CommandSpec((sys.executable, '-c', "from pathlib import Path; print(Path('a.txt').read_text())"), 'read')
        edit = CommandSpec((sys.executable, '-c', "from pathlib import Path; Path('other.txt').write_text('new')"), 'edit')
        action = MacroAction('id', 'read', '', '', '', (read,), ())
        outcome = self.env.execute(first, action, 3)
        outcome = self.env.execute(outcome.resulting_snapshot, replace(action, commands=(edit, read)), 3)
        m = self.rec.summary()
        self.assertEqual(m['tool_calls'], 3)
        self.assertEqual(m['interaction_rounds'], 2)
        self.assertEqual(m['redundant_tool_calls'], 1)
        self.assertEqual(m['mechanical_repeat_calls'], 0)

    def test_python_ast_rejects_side_effects_and_arbitrary_code(self):
        for code in ("print('ok')", "print(open('x', 'w').read())", "import os; print(open('x').read())",
                     "print(open(input()).read())", "print(open('x').read()); print('more')"):
            self.assertIsNone(python_read(['-c', code]))
        self.assertEqual(python_read(['-c', "print(open('a.txt').read())"]), ['a.txt'])


class RedundancyReportTests(unittest.TestCase):
    def test_large_linux_binary_supported_without_relaxing_task_file_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'large-python'
            with path.open('wb') as stream:
                stream.truncate(LIMIT + 128)
            self.assertIsNone(file_state(path))
            from bestfgs.experience import _file_digest
            self.assertIsNone(_file_digest(path))
            self.assertIsNotNone(_file_digest(path, max_bytes=256 * 1024 * 1024))
            first = binary_state(path)
            self.assertIsNotNone(first)
            with patch('bestfgs.redundancy.file_state', side_effect=AssertionError('unchanged binary must be cached')):
                self.assertEqual(binary_state(path), first)
            with path.open('r+b') as stream:
                stream.write(b'changed')
            self.assertNotEqual(binary_state(path), first)

    def test_legacy_data_is_not_relabelled_or_zero_filled(self):
        self.assertIsNone(aggregate_redundancy([{'tool_calls': 3, 'redundant_tool_calls': 1,
                                              'trace_complete': True}])['tool_call_redundancy_rate'])

    def test_comparison_uses_actual_new_metric_not_mechanical(self):
        a = fixtures.evaluated('bestfgs', (True, True), redundant=(1, 2))
        b = fixtures.evaluated('raw', (True, True), redundant=(2, 4))
        for arm in (a, b):
            for task in arm['tasks']:
                m = task['comparison_metrics']
                m.update(redundancy_version='reusable-evidence-v1', redundancy_unknown_calls=1,
                         mechanical_repeat_calls=0)
        result = comparison.compare(a, b, repeats=200)
        cohort = result['efficiency_cohorts']['both_officially_resolved_pairs']
        self.assertEqual(cohort['tool_call_redundancy_rate_reduction']['estimate'], .5)
        self.assertIsNone(cohort['mechanical_repeat_rate_reduction']['estimate'])
        self.assertTrue(result['targets']['tool_call_redundancy_minus_50_percent_on_joint_success']['point_estimate_meets_target'])
        self.assertEqual(cohort['bestfgs']['redundancy_unknown_calls'], 2)
        self.assertEqual(cohort['bestfgs']['tool_call_redundancy_rate'], 3 / 12)
        self.assertEqual(cohort['bestfgs']['redundancy_classification_coverage'], 10 / 12)


if __name__ == '__main__':
    unittest.main()
