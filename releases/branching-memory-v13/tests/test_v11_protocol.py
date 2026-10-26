"""Offline contracts: v11 fixed budgets and treatments may not reuse older Raw data."""
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


class EvidenceProtocolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        seed = self.root / 'seed'
        seed.mkdir()
        (seed / 'app.py').write_text('x = 1\n', encoding='utf-8')
        self.python = self.root / 'env/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b'fingerprint-only; never executed')
        self.manifest = self.root / 'manifest.json'
        atomic_write_json(self.manifest, {'schema_version': 1, 'benchmark': 'custom', 'tasks': [
            {'id': 'dev-one', 'goal': 'Repair public behavior', 'workspace': str(seed),
             'task_python': str(self.python)}]})
        self.output = self.root / 'fresh-results'

    def ablation_args(self, *extra):
        return ['--study', 'evidence', '--task-manifest', str(self.manifest), '--output-root', str(self.output),
                '--python', str(self.python), '--model', 'fixture-model', *extra]

    def plan(self, *extra):
        with patch.object(ablation, 'implementation_identity', return_value={'fixture': 'stable'}):
            return ablation.build_plan(ablation.parser().parse_args(self.ablation_args(*extra)))

    def test_default_is_four_arm_evidence_and_explicit_treatments(self):
        plan = self.plan()
        protocol = plan['protocol']
        self.assertEqual(protocol['engine'], 'evidence')
        self.assertEqual(protocol['runtime_version'], ablation.RUNTIME_PROTOCOL)
        self.assertFalse(protocol['historical_baseline_reuse'])
        self.assertEqual(set(protocol['modes']), set(ablation.EVIDENCE_MODES))
        jobs = list(ablation.jobs(plan))
        self.assertEqual(len(jobs), 4)
        self.assertEqual(len({job['output_root'] for job in jobs}), 4)
        for job in jobs:
            config = ablation.EVIDENCE_ARMS[job['mode']]
            self.assertEqual(job['argv'][job['argv'].index('--method') + 1], config['method'])
            self.assertEqual(job['extra'][:len(protocol['common_agent_args'])], protocol['common_agent_args'])
            self.assertEqual(job['extra'][job['extra'].index('--experience-mode') + 1], config['experience_mode'])
            self.assertEqual('--disable-evidence-branching' in job['extra'], not config['branching_enabled'])
        self.assertFalse(self.output.exists())

    def test_legacy_requires_explicit_engine_and_has_distinct_protocol(self):
        new, old = self.plan(), self.plan('--engine', 'legacy')
        self.assertNotEqual(new['protocol_sha256'], old['protocol_sha256'])
        self.assertEqual(old['protocol']['modes'], list(ablation.MODES))
        self.assertEqual(old['protocol']['version'], ablation.LEGACY_PROTOCOL_VERSION)
        for job in ablation.jobs(old):
            self.assertEqual(job['extra'][job['extra'].index('--engine') + 1], 'legacy')

    def test_schedule_reproducible_and_no_provider_calls_by_default(self):
        self.assertEqual(self.plan()['protocol_sha256'], self.plan()['protocol_sha256'])
        capture = io.StringIO()
        with patch.object(ablation, 'execute_plan', side_effect=AssertionError('must not execute')), redirect_stdout(capture):
            self.assertEqual(ablation.main(self.ablation_args()), 0)
        payload = json.loads(capture.getvalue())
        self.assertFalse(payload['execution_requested'])
        self.assertEqual(len(payload['commands']), 4)
        self.assertFalse(self.output.exists())

    def paired_args(self):
        return SimpleNamespace(prepared_root=self.root / 'prepared', output_root=self.output,
                               model='fixture-model', base_url='https://api.deepseek.com', temperature=.2,
                               reasoning_effort='high', max_iterations=24, max_tool_calls=80,
                               max_commands=4, top_p=None, task_timeout=14400, shard_count=1)

    def test_paired_protocol_freezes_budget_meaning_and_actual_arm_flags(self):
        args = self.paired_args()
        plan = {'tasks': [{'instance_id': 'one'}], 'plan_sha256': 'fixed', 'dataset': 'fixture', 'split': 'dev'}
        with patch.object(paired, 'implementation_sha256', return_value='fixture'):
            one, prepared, missing = paired.protocol_for(args, plan)
            two, _, _ = paired.protocol_for(args, plan)
        self.assertEqual(canonical_sha256(one), canonical_sha256(two))
        self.assertFalse(prepared)
        self.assertEqual(missing, ['one'])
        self.assertEqual(one['common_args'][:2], ['--provider', 'deepseek'])
        self.assertEqual(one['method_args']['raw'], ['--engine', 'evidence', '--experience-mode', 'off',
                                                     '--blocking-memory', 'off', '--disable-evidence-branching'])
        self.assertEqual(one['method_args']['bestfgs'], ['--engine', 'graph', '--experience-mode', 'conditioned',
                                                         '--blocking-memory', 'off'])
        self.assertIn('decision turns', one['budget_semantics']['max_iterations'])
        self.assertIn('not decision turns', one['budget_semantics']['interaction_rounds'])
        self.assertFalse(one['historical_baseline_reuse'])

    def test_internal_success_never_becomes_official_result(self):
        row = {'id': 'one', 'status': 'completed', 'decision_turns': 3, 'elapsed_seconds': 0,
               'comparison_metrics': None, 'model_usage': None,
               'experience_report': None, 'official_resolved': True}
        result = ablation.aggregate([row])
        self.assertIsNone(result['official_success_rate'])
        self.assertEqual(result['official_unknown'], 1)
        self.assertEqual(result['mean_decision_turns'], 3)
        self.assertIsNone(result['mean_interaction_rounds'])

    def test_old_raw_artifact_rejected_and_v11_fields_required(self):
        plan = self.plan()
        atomic_write_json(self.output / 'ablation-plan.json', plan)
        job = next(job for job in ablation.jobs(plan) if job['mode'] == 'raw')
        output = Path(job['output_root'])
        attempt = output / job['id'] / 'attempt-fixture'
        result_path = attempt / 'agent-result.json'
        result = {'submitted': True, 'succeeded': False,
                  'comparison_metrics': {'tool_calls': 1}, 'decision_turns': 1}
        atomic_write_json(result_path, result)
        atomic_write_json(output / job['id'] / 'status.json', {'status': 'completed', 'attempt': str(attempt)})
        row = ablation.collect_row(self.output, job)
        self.assertEqual(row['status'], 'artifact_error')
        self.assertIsNone(row['comparison_metrics'])
        result.update(runtime_version=ablation.RUNTIME_PROTOCOL, experience_mode='off', branching_enabled=False,
                      blocking_memory_mode='off')
        atomic_write_json(result_path, result)
        row = ablation.collect_row(self.output, job)
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['decision_turns'], 1)
        result['decision_turns'] = plan['protocol']['budget_limits']['decision_turns'] + 1
        atomic_write_json(result_path, result)
        self.assertEqual(ablation.collect_row(self.output, job)['status'], 'artifact_error')

    def test_pair_completion_gate_rejects_old_results_and_overspending(self):
        args = self.paired_args()
        protocol = {'runtime_version': paired.RUNTIME_PROTOCOL, 'method_configurations': paired.ARM_CONFIGURATIONS}
        state = {'status': 'completed', 'comparison_metrics': {'trace_complete': True, 'tool_calls': 1}}
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'search_error')
        state.update(status='completed', runtime_version=paired.ARM_CONFIGURATIONS['raw']['runtime_version'],
                     search_algorithm='raw_cli',
                     experience_mode='off', branching_enabled=False, blocking_memory_mode='off', decision_turns=2)
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'completed')
        state['decision_turns'] = args.max_iterations + 1
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'search_error')
        state.update(status='completed', decision_turns=2)
        state['comparison_metrics']['tool_calls'] = args.max_tool_calls + 1
        self.assertEqual(paired.validate_completed_state(args, protocol, 'raw', state)['status'], 'search_error')


if __name__ == '__main__':
    unittest.main()
