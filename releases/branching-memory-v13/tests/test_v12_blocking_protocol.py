"""No paid calls: blocking treatment assignment, frozen provenance and accounting."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_comparison as paired
import run_experience_ablation as ablation
from benchmark_runtime import atomic_write_json, canonical_sha256


class BlockingProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        seed = self.root / 'seed'
        seed.mkdir()
        (seed / 'source.py').write_text('value = 1\n', encoding='utf-8')
        self.python = self.root / 'env/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b'fixture-only; never executed')
        self.manifest = self.root / 'manifest.json'
        self.output = self.root / 'fresh-results'
        atomic_write_json(self.manifest, {'schema_version': 1, 'benchmark': 'custom', 'tasks': [
            {'id': 'one', 'goal': 'Fix public behavior', 'workspace': str(seed), 'task_python': str(self.python)},
            {'id': 'two', 'goal': 'Fix another public behavior', 'workspace': str(seed), 'task_python': str(self.python)}]})
        self.identity = patch.object(ablation, 'implementation_identity', return_value={'fixture': 'stable'})
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def argv(self, *extra):
        return ['--task-manifest', str(self.manifest), '--output-root', str(self.output),
                '--python', str(self.python), '--model', 'fixture-model', *extra]

    def plan(self, *extra):
        return ablation.build_plan(ablation.parser().parse_args(self.argv(*extra)))

    def test_default_is_three_arms_with_no_other_mechanism_confounder(self):
        plan = self.plan()
        protocol = plan['protocol']
        self.assertEqual(protocol['version'], 'blocking-memory-development-v12')
        self.assertEqual(protocol['runtime_version'], 'blocking-cli-v12')
        self.assertEqual(protocol['study'], 'blocking')
        self.assertEqual(protocol['modes'], list(ablation.BLOCKING_MODES))
        self.assertEqual(protocol['expected_ids'], ['one', 'two'])
        self.assertFalse(protocol['historical_baseline_reuse'])
        jobs = list(ablation.jobs(plan))
        self.assertEqual(len(jobs), 6)
        self.assertEqual(len({j['output_root'] for j in jobs}), 6)
        for mode, blocker_mode in [('raw', 'off'), ('blocker_advisory', 'advisory'), ('blocker_control', 'control')]:
            configuration = protocol['arm_configurations'][mode]
            self.assertEqual(configuration['experience_mode'], 'off')
            self.assertIs(configuration['branching_enabled'], False)
            self.assertEqual(configuration['blocking_memory_mode'], blocker_mode)
            for job in [j for j in jobs if j['mode'] == mode]:
                self.assertEqual(job['extra'][job['extra'].index('--blocking-memory') + 1], blocker_mode)
                self.assertEqual(job['extra'][job['extra'].index('--experience-mode') + 1], 'off')
                self.assertIn('--disable-evidence-branching', job['extra'])
                self.assertEqual(job['extra'][:len(protocol['common_agent_args'])], protocol['common_agent_args'])
        self.assertIn('diagnostic CLI', protocol['budget_semantics']['blocking_diagnostics'])
        self.assertFalse(self.output.exists())

    def test_default_plan_does_not_create_results_or_execute(self):
        captured = io.StringIO()
        with patch.object(ablation, 'execute_plan', side_effect=AssertionError('no execution')), redirect_stdout(captured):
            self.assertEqual(ablation.main(self.argv()), 0)
        self.assertEqual(len(json.loads(captured.getvalue())['commands']), 6)
        self.assertFalse(self.output.exists())

    def test_evidence_study_explicitly_turns_blocking_off(self):
        blocking, evidence = self.plan(), self.plan('--study', 'evidence')
        self.assertNotEqual(blocking['protocol_sha256'], evidence['protocol_sha256'])
        self.assertEqual(evidence['protocol']['version'], ablation.EVIDENCE_PROTOCOL_VERSION)
        self.assertEqual(len(list(ablation.jobs(evidence))), 8)
        self.assertTrue(all(c['blocking_memory_mode'] == 'off'
                            for c in evidence['protocol']['arm_configurations'].values()))

    def write_result(self, plan, mode, **overrides):
        atomic_write_json(self.output / 'ablation-plan.json', plan)
        job = next(j for j in ablation.jobs(plan) if j['mode'] == mode)
        attempt = Path(job['output_root']) / job['id'] / 'attempt-fixture'
        configuration = plan['protocol']['arm_configurations'][mode]
        result = {'runtime_version': 'blocking-cli-v12', 'experience_mode': configuration['experience_mode'],
                  'branching_enabled': configuration['branching_enabled'],
                  'blocking_memory_mode': configuration['blocking_memory_mode'], 'decision_turns': 3,
                  'blocking_memory_metrics': {'diagnostic_tool_calls': 1, 'deferred_actions': 2},
                  'blocking_memory_report': {'mode': configuration['blocking_memory_mode']}}
        result.update(overrides)
        atomic_write_json(attempt / 'agent-result.json', result)
        atomic_write_json(Path(job['output_root']) / job['id'] / 'status.json',
                          {'status': 'completed', 'attempt': str(attempt)})
        return ablation.collect_row(self.output, job)

    def test_wrong_missing_or_old_blocker_provenance_is_rejected(self):
        plan = self.plan()
        self.assertEqual(self.write_result(plan, 'blocker_control')['status'], 'completed')
        for overrides in ({'blocking_memory_mode': None}, {'blocking_memory_mode': 'advisory'},
                          {'runtime_version': 'evidence-cli-v11'}, {'experience_mode': 'conditioned'},
                          {'branching_enabled': True}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.write_result(plan, 'blocker_control', **overrides)['status'], 'artifact_error')

    def test_blocker_counts_are_diagnostics_not_success_or_savings(self):
        row = self.write_result(self.plan(), 'blocker_control')
        summary = ablation.aggregate([row])
        self.assertEqual(summary['recorded_blocking_memory_metrics']['diagnostic_tool_calls']['recorded_total'], 1)
        self.assertEqual(summary['recorded_blocking_memory_metrics']['deferred_actions']['recorded_total'], 2)
        self.assertEqual(summary['blocking_memory_reports_available'], 1)
        self.assertIsNone(summary['false_block_rate'])
        self.assertIsNone(summary['causal_tool_calls_saved'])
        self.assertIsNone(summary['official_success_rate'])
        self.assertIsNone(summary['tool_calls'])
        self.assertIsNone(summary['mean_interaction_rounds'])

    def test_missing_diagnostics_not_silently_zero_filled(self):
        rows = [self.write_result(self.plan(), 'blocker_control'),
                {'id': 'two', 'status': 'not_started', 'blocking_memory_metrics': None}]
        entry = ablation.aggregate(rows)['recorded_blocking_memory_metrics']['deferred_actions']
        self.assertEqual(entry, {'recorded_total': 2, 'tasks_recorded': 1, 'complete': False})

    def test_unknown_study_or_historical_protocol_cannot_be_summarized(self):
        plan = self.plan()
        plan['protocol'].pop('study')
        plan['protocol_sha256'] = canonical_sha256(plan['protocol'])
        atomic_write_json(self.output / 'ablation-plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'Unknown ablation study'):
            ablation.summarize(self.output)

    def test_v13_pair_assignment_restores_graph_and_keeps_raw_sequential(self):
        self.assertEqual(paired.method_args('bestfgs'), ['--engine', 'graph', '--experience-mode', 'conditioned',
                                                        '--blocking-memory', 'off'])
        self.assertIn('--disable-evidence-branching', paired.method_args('raw'))
        args = SimpleNamespace(max_iterations=24, max_tool_calls=80)
        protocol = {'runtime_version': paired.RUNTIME_PROTOCOL, 'method_configurations': paired.ARM_CONFIGURATIONS}
        state = {'status': 'completed', 'comparison_metrics': {'trace_complete': True, 'tool_calls': 3},
                 'runtime_version': paired.ARM_CONFIGURATIONS['raw']['runtime_version'],
                 'search_algorithm': 'raw_cli', 'experience_mode': 'off',
                 'branching_enabled': False, 'blocking_memory_mode': 'control', 'decision_turns': 3}
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'search_error')
        state.update(status='completed', blocking_memory_mode='off')
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
