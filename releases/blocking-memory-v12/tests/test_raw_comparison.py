from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark_runtime import atomic_write_json, canonical_sha256
import compare_experiments as report
import run_comparison as paired
import run_notebook
from bestfgs.cli_config import model_config_from_args
from bestfgs.__main__ import build_parser
from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.experiment_metrics import ExperimentRecorder, METRIC_VERSION, workspace_digest, summarize_trace
from bestfgs.models import CommandSpec, CommandResult, MacroAction, TaskSpec, ModelCallError
from bestfgs.raw_baseline import parse_turn, run_raw
from bestfgs.retrac_adapter import RetracModelConfig, RetracPolicyAdapter, OpenAICompatibleJSONClient, parse_cli_commands, _coalesce_streaming_body
from test_swe_batch import plan as make_plan


def command(source="print('ok')"):
    return CommandSpec((sys.executable, '-c', source), 'test')


def envelope(commands, verification=(), direction='ignored'):
    return MacroAction('id', 'test', '', direction, direction, tuple(commands), tuple(verification))


def wire(source="print('ok')"):
    return {'argv': [sys.executable, '-c', source], 'description': 'test'}


class FakeClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.prompts = []

    def complete_json(self, **kwargs):
        self.prompts.append(kwargs)
        value = next(self.payloads)
        if isinstance(value, Exception):
            raise value
        return value

    def usage_summary(self):
        return {'model_calls': len(self.prompts), 'api_requests': len(self.prompts)}


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / 'seed'
        self.seed.mkdir()
        (self.seed / 'file.txt').write_text('initial')
        self.recorder = ExperimentRecorder(self.root / 'metrics.jsonl')
        self.environment = ForkedWorkspaceEnvironment(self.seed, self.root / 'runs', recorder=self.recorder)
        self.snapshot = self.environment.initial_snapshot()

    def execute(self, commands, verification=(), direction='ignored'):
        result = self.environment.execute(self.snapshot, envelope(commands, verification, direction), 4)
        self.snapshot = result.resulting_snapshot
        return result

    def test_repeats_cross_semantic_directions_and_include_final_verification(self):
        self.execute([command()], [command()])
        self.execute([command()], direction='different-semantic-direction')
        self.environment.verify(self.snapshot, (command(),))
        m = self.recorder.summary()
        self.assertEqual(m['interaction_rounds'], 3)
        self.assertEqual(m['tool_calls'], 4)
        self.assertEqual(m['mechanical_repeat_calls'], 3)
        self.assertEqual(m['mechanical_repeat_rate'], .75)
        self.assertEqual(m['redundant_tool_calls'], 0)
        self.assertEqual(m['redundancy_unknown_calls'], 4)
        self.assertEqual(m['tool_calls_by_phase'], {'action': 2, 'functional_verification': 1, 'final_verification': 1})
        self.assertTrue(m['trace_complete'])

    def test_changed_files_reset_same_command_repeat(self):
        self.execute([command()])
        self.execute([command("from pathlib import Path; Path('file.txt').write_text('new')")])
        self.execute([command()])
        self.assertEqual(self.recorder.summary()['redundant_tool_calls'], 0)

    def test_automatic_syntax_gate_is_not_a_model_tool_call(self):
        outcome = self.execute([command("from pathlib import Path; Path('code.py').write_text('x=1')")])
        self.assertTrue(outcome.validation_results)
        self.assertEqual(self.recorder.summary()['tool_calls'], 1)

    def test_zero_tools_undefined_rate(self):
        self.environment.verify(self.snapshot, ())
        m = self.recorder.summary()
        self.assertEqual(m['interaction_rounds'], 0)
        self.assertIsNone(m['tool_call_redundancy_rate'])

    def test_blocked_command_is_an_attempt_and_round(self):
        self.execute([CommandSpec(('rm', 'file.txt'), 'blocked')])
        m = self.recorder.summary()
        self.assertEqual(m['blocked_tool_calls'], 1)
        self.assertEqual(m['tool_calls'], 1)
        self.assertTrue((self.seed / 'file.txt').exists())

    def test_incomplete_command_not_silently_dropped(self):
        def fail():
            raise RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            self.recorder.command(self.environment, Path(self.snapshot.location), command(), fail)
        m = self.recorder.summary()
        self.assertEqual(m['tool_calls'], 1)
        self.assertEqual(m['completed_tool_calls'], 0)
        self.assertFalse(m['trace_complete'])
        self.assertIsNone(m['tool_call_redundancy_rate'])

    def test_output_changes_are_not_redundant(self):
        for text in ('a', 'b'):
            self.recorder.command(self.environment, Path(self.snapshot.location), command(),
                                  lambda: CommandResult(command(), 0, text, '', 0.))
        self.assertEqual(self.recorder.summary()['redundant_tool_calls'], 0)

    def test_different_timeout_is_not_same_command(self):
        self.execute([CommandSpec(command().argv, 'one', timeout_seconds=5),
                      CommandSpec(command().argv, 'two', timeout_seconds=6)])
        self.assertEqual(self.recorder.summary()['redundant_tool_calls'], 0)

    def test_git_and_test_cache_do_not_change_metric_state(self):
        before = workspace_digest(self.seed)
        (self.seed / '.git').mkdir()
        (self.seed / '.git/index').write_text('cache')
        (self.seed / '.pytest_cache').mkdir()
        (self.seed / '.pytest_cache/log').write_text('cache')
        self.assertEqual(before, workspace_digest(self.seed))

    def test_trace_contains_hashes_not_command_or_output_secrets(self):
        self.execute([command("print('secret-sentinel-value')")])
        self.assertNotIn('secret-sentinel-value', self.recorder.path.read_text())

    def test_truncated_trace_is_marked_incomplete(self):
        with self.recorder.path.open('ab') as stream:
            stream.write(b'{"event":')
        self.assertFalse(summarize_trace(self.recorder.path)['trace_complete'])


class RawTests(unittest.TestCase):
    setUp = RecorderTests.setUp
    def run_client(self, payloads, tools=8, iterations=8):
        client = FakeClient(payloads)
        env = ForkedWorkspaceEnvironment(self.seed, self.root / 'raw', recorder=self.recorder)
        config = RetracModelConfig(provider='deepseek', api_key='fake-only', model_name='deepseek-flash', base_url='https://api.deepseek.com')
        with patch('bestfgs.retrac_adapter.RetracPolicyAdapter', side_effect=AssertionError('No policy allowed')):
            result = run_raw(TaskSpec.create('repair'), env, client, config, max_iterations=iterations,
                             max_tool_calls=tools, max_commands=4)
        return result, client

    def test_plain_sequential_history_and_submission(self):
        result, client = self.run_client([
            {'done': False, 'commands': [wire("from pathlib import Path; Path('file.txt').write_text('fixed')")]},
            {'done': False, 'commands': [wire("from pathlib import Path; print(Path('file.txt').read_text())")]},
            {'done': True},
        ])
        self.assertEqual(result['stop_reason'], 'submitted')
        self.assertFalse(result['succeeded'])
        self.assertEqual(result['total_tool_calls'], 2)
        self.assertEqual(result['model_usage']['model_calls'], 3)
        self.assertEqual((Path(result['best_workspace']) / 'file.txt').read_text(), 'fixed')
        self.assertEqual((self.seed / 'file.txt').read_text(), 'initial')
        prompt = json.loads(client.prompts[2]['user_prompt'])
        self.assertEqual(len(prompt['transcript']), 4)
        self.assertIn('fixed', prompt['transcript'][-1]['content'])
        self.assertEqual(self.recorder.summary()['interaction_rounds'], 2)

    def test_budget_counts_verification_too_and_does_not_call_model_after_exhaustion(self):
        result, client = self.run_client([{'done': False, 'commands': [wire()], 'verification_commands': [wire()]}], tools=2)
        self.assertEqual(result['stop_reason'], 'tool_budget')
        self.assertEqual(len(client.prompts), 1)
        self.assertEqual(result['total_tool_calls'], 2)

    def test_model_outage_no_search_recovery_or_solution_retry(self):
        result, client = self.run_client([ModelCallError('outage')])
        self.assertEqual(result['stop_reason'], 'model_unavailable')
        self.assertEqual(result['total_tool_calls'], 0)
        self.assertEqual(len(client.prompts), 1)

    def test_schema_repairs_are_counted_as_model_calls_not_cli_rounds(self):
        result, _ = self.run_client([{'done': 'bad'}, {'done': True}])
        self.assertEqual(result['model_usage']['model_calls'], 2)
        self.assertEqual(self.recorder.summary()['interaction_rounds'], 0)

    def test_submission_cannot_hide_unexecuted_commands(self):
        with self.assertRaises(ValueError):
            parse_turn({'done': True, 'commands': [wire()]}, RetracModelConfig(api_key='fake', model_name='fake', base_url='https://api.deepseek.com'))

    def test_shared_command_parser_and_model_parameters(self):
        config = RetracModelConfig(api_key='fake', model_name='fake', base_url='https://api.deepseek.com')
        policy = RetracPolicyAdapter(config)
        self.assertEqual(policy._parse_commands([wire()]), parse_cli_commands([wire()], config))
        args = build_parser().parse_args(['--goal', 'repair', '--workspace', str(self.seed), '--provider', 'deepseek',
                                         '--model', 'deepseek-flash', '--reasoning-effort', 'high', '--solve-reasoning-effort', 'high'])
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake'}):
            actual = model_config_from_args(args)
        self.assertEqual((actual.provider, actual.model_name, actual.temperature, actual.solve_reasoning_effort),
                         ('deepseek', 'deepseek-flash', .2, 'high'))

    def test_raw_main_real_environment_and_result_contract(self):
        from bestfgs import raw_baseline
        client = FakeClient([{'done': False, 'commands': [wire("from pathlib import Path; Path('file.txt').write_text('fixed')")]}, {'done': True}])
        output = io.StringIO()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake'}), patch.object(raw_baseline, 'OpenAICompatibleJSONClient', return_value=client), redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = raw_baseline.main(['--workspace', str(self.seed), '--run-root', str(self.root / 'entrypoint'),
                                     '--goal', 'repair', '--provider', 'deepseek', '--comparison-metrics', '--quiet'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['stop_reason'], 'submitted')
        self.assertEqual(result['comparison_metrics']['tool_calls'], 1)
        self.assertEqual((Path(result['best_workspace']) / 'file.txt').read_text(), 'fixed')

    def test_model_output_failure_is_distinct_from_transport_failure(self):
        config = RetracModelConfig(api_key='fake', model_name='fake', base_url='https://api.deepseek.com', request_attempts=1)
        client = OpenAICompatibleJSONClient(config)
        invalid = json.dumps({'model': 'actual-model-id', 'choices': [{'message': {'content': 'invalid JSON'}}]}).encode()
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', return_value=invalid), self.assertRaises(ModelCallError):
            client.complete_json(system_prompt='test', user_prompt='test')
        self.assertEqual(client.usage_summary()['last_failure_kind'], 'model_output')
        self.assertEqual(client.usage_summary()['response_models'], ['actual-model-id'])
        self.assertEqual(client.usage_summary()['usage_missing_responses'], 1)
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', side_effect=TimeoutError()), self.assertRaises(ModelCallError):
            client.complete_json(system_prompt='test', user_prompt='test')
        self.assertEqual(client.usage_summary()['last_failure_kind'], 'transport')

    def test_stream_preserves_model_version_evidence(self):
        event = {'model': 'actual', 'system_fingerprint': 'revision', 'choices': [{'delta': {'content': '{"ok":true}'}}]}
        payload = json.loads(_coalesce_streaming_body(('data: ' + json.dumps(event) + '\n\ndata: [DONE]\n').encode()))
        self.assertEqual(payload['model'], 'actual')
        self.assertEqual(payload['system_fingerprint'], 'revision')


def evaluated(method, successes=(True, False), rounds=(2, 4), calls=(4, 8), redundant=(1, 2)):
    ids = ['sample__task-1', 'sample__task-2']
    protocol = {'metric_version': METRIC_VERSION, 'expected_ids': ids, 'same_everything': 'test'}
    tasks = []
    for i, identity in enumerate(ids):
        tasks.append({'instance_id': identity, 'search_status': 'completed', 'verdict': 'resolved' if successes[i] else 'unresolved',
                      'grading_script_sha256': 'same-script-' + identity,
                      'resolved': successes[i], 'official_report_available': True, 'attempt_count': 1,
                      'comparison_metrics': {'metric_version': METRIC_VERSION, 'trace_complete': True,
                                             'redundancy_version': 'reusable-evidence-v1', 'redundancy_unknown_calls': 0,
                                             'interaction_rounds': rounds[i], 'tool_calls': calls[i],
                                             'redundant_tool_calls': redundant[i]}})
    return {'comparison': {'method': method, 'protocol': protocol, 'protocol_sha256': canonical_sha256(protocol)},
            'evaluation_parameters': {'runtime': 'same-official-version', 'timeout': 1800}, 'tasks': tasks}


class ComparisonTests(unittest.TestCase):
    def test_official_test_script_mismatch_is_rejected(self):
        a, b = evaluated('bestfgs'), evaluated('raw')
        b['tasks'][0]['grading_script_sha256'] = 'different'
        with self.assertRaises(ValueError):
            report.compare(a, b)

    def test_paired_batch_exports_both_methods_and_resume_never_reruns_completed(self):
        from evaluate_swe_batch import read_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan()
            manifest = root / 'plan.json'
            atomic_write_json(manifest, plan)
            task = plan['tasks'][0]
            identity = task['instance_id']
            directory = root / 'prepared' / 'prepared' / identity
            ready = {'id': identity, 'base_commit': task['base_commit'], 'recipe_sha256': canonical_sha256(task),
                     'goal': task['problem_statement'], 'seed_sha256': 'seed', 'prepared_commit': 'c' * 40,
                     'task_python': sys.executable, 'workspace': str(root / 'seed')}
            atomic_write_json(directory / 'ready.json', ready)
            (directory / 'pip-freeze.txt').write_text('fake-freeze')
            def checked(command, **kwargs):
                output = Path(command[command.index('--output-root') + 1])
                attempt = output / identity / 'attempt-test'
                recorder = ExperimentRecorder(attempt / 'snapshots/cli-metrics.jsonl')
                atomic_write_json(output / identity / 'status.json', {'status': 'completed', 'attempt': str(attempt)})
                method = command[command.index('--method') + 1]
                atomic_write_json(attempt / 'agent-result.json', {
                    'succeeded': False, 'stop_reason': 'submitted', 'comparison_metrics': recorder.summary(),
                    'runtime_version': paired.RUNTIME_PROTOCOL, 'decision_turns': 1,
                    'search_algorithm': paired.ARM_CONFIGURATIONS[method]['algorithm'],
                    'experience_mode': paired.ARM_CONFIGURATIONS[method]['experience_mode'],
                    'blocking_memory_mode': paired.ARM_CONFIGURATIONS[method]['blocking_memory_mode'],
                    'branching_enabled': paired.ARM_CONFIGURATIONS[method]['branching_enabled']})
                (output / 'predictions.jsonl').write_text(json.dumps({'instance_id': identity, 'model_name_or_path': 'fake', 'model_patch': 'diff'}) + '\n')
            argv = ['run', '--plan', str(manifest), '--prepared-root', str(root / 'prepared'), '--output-root', str(root / 'out')]
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake'}), patch.object(paired, 'check_prepared'), patch.object(paired, 'checked', side_effect=checked) as execute, redirect_stdout(io.StringIO()):
                self.assertEqual(paired.main(argv), 0)
                self.assertEqual(execute.call_count, 2)
                self.assertEqual(paired.main(argv), 0)
                self.assertEqual(execute.call_count, 2)
            locks = []
            for method in ('bestfgs', 'raw'):
                _, rows, states, bundle = read_bundle(root / 'out' / method / 'evaluation-bundle.zip')
                self.assertEqual(rows[0]['model_name_or_path'], method + '-deepseek')
                self.assertEqual(states[0]['comparison_metrics']['metric_version'], METRIC_VERSION)
                locks.append(bundle['comparison']['protocol_sha256'])
            self.assertEqual(locks[0], locks[1])

    def test_report_official_success_and_micro_denominators(self):
        a = evaluated('bestfgs', (True, True), (2, 4), (4, 8), (1, 2))
        b = evaluated('raw', (True, False), (4, 8), (4, 8), (2, 4))
        a['tasks'][0]['agent_succeeded'] = False
        result = report.compare(a, b, repeats=200)
        self.assertEqual(result['success']['difference_percentage_points'], 50)
        self.assertEqual(result['success']['relative_improvement'], 1)
        cohort = result['efficiency_cohorts']['all_complete_single_attempt_pairs']
        self.assertEqual(cohort['round_reduction']['estimate'], .5)
        self.assertEqual(cohort['repeat_rate_reduction']['estimate'], .5)
        self.assertEqual(result['efficiency_cohorts']['both_officially_resolved_pairs']['bestfgs']['n'], 1)

    def test_legacy_metrics_rejected(self):
        with self.assertRaises(ValueError):
            report.compare({'tasks': []}, {'tasks': []})

    def test_different_api_or_harness_rejected(self):
        for field in ('protocol', 'harness'):
            a, b = evaluated('bestfgs'), evaluated('raw')
            if field == 'protocol':
                b['comparison']['protocol']['model'] = 'different'
                b['comparison']['protocol_sha256'] = canonical_sha256(b['comparison']['protocol'])
            else:
                b['evaluation_parameters']['timeout'] = 10
            with self.assertRaises(ValueError):
                report.compare(a, b)

    def test_missing_evaluation_is_unknown_not_failure(self):
        a, b = evaluated('bestfgs'), evaluated('raw')
        b['tasks'][1].update(verdict='evaluation_error', resolved=None, official_report_available=False)
        result = report.compare(a, b, repeats=200)
        self.assertIsNone(result['success']['raw']['rate'])
        self.assertEqual(result['success']['raw']['rate_bounds'], [.5, 1])
        self.assertFalse(result['targets']['valid_complete_protocol'])

    def test_zero_call_rate_and_zero_baseline_reduction_undefined(self):
        a, b = evaluated('bestfgs', calls=(0, 0), redundant=(0, 0)), evaluated('raw', calls=(0, 0), redundant=(0, 0))
        result = report.compare(a, b, repeats=200)
        cohort = result['efficiency_cohorts']['all_complete_single_attempt_pairs']
        self.assertIsNone(cohort['repeat_rate_reduction']['estimate'])
        self.assertIsNone(cohort['bestfgs']['repeat_rate_micro'])

    def test_incomplete_trace_and_retry_not_silently_accepted(self):
        a, b = evaluated('bestfgs'), evaluated('raw')
        a['tasks'][0]['comparison_metrics']['trace_complete'] = False
        b['tasks'][1]['attempt_count'] = 2
        result = report.compare(a, b, repeats=200)
        self.assertEqual(len(result['excluded_efficiency_ids']), 2)
        self.assertFalse(result['targets']['valid_complete_protocol'])

    def test_id_denominator_cannot_shrink(self):
        a, b = evaluated('bestfgs'), evaluated('raw')
        b['tasks'].pop()
        with self.assertRaises(ValueError):
            report.compare(a, b)

    def test_plan_missing_environments_never_calls_api_or_creates_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / 'plan.json'
            atomic_write_json(manifest, make_plan())
            with redirect_stdout(io.StringIO()), patch.object(paired, 'run_one', side_effect=AssertionError('No paid calls')):
                code = paired.main(['plan', '--plan', str(manifest), '--prepared-root', str(root / 'prepared'), '--output-root', str(root / 'comparison')])
            self.assertEqual(code, 2)
            self.assertFalse((root / 'comparison').exists())

    def test_no_all_ready_no_paid_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / 'plan.json'
            atomic_write_json(manifest, make_plan())
            with patch.object(paired, 'run_one', side_effect=AssertionError('No paid calls')), self.assertRaises(ValueError):
                paired.main(['run', '--plan', str(manifest), '--prepared-root', str(root / 'prepared'), '--output-root', str(root / 'comparison')])

    def test_raw_notebook_selects_raw_module_and_does_not_require_internal_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'seed').mkdir()
            manifest = root / 'tasks.json'
            atomic_write_json(manifest, {'schema_version': 1, 'benchmark': 'custom',
                                        'tasks': [{'id': 'one', 'goal': 'repair', 'workspace': str(root / 'seed')}]})
            def execute(command, directory, env, timeout):
                self.assertEqual(command[2], 'bestfgs.raw_baseline')
                snapshot = directory / 'snapshots/candidate'
                snapshot.mkdir(parents=True)
                atomic_write_json(directory / 'agent-result.json', {'succeeded': False, 'best_workspace': str(snapshot), 'stop_reason': 'submitted'})
                return 1
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake'}), patch.object(run_notebook, 'execute', side_effect=execute), redirect_stdout(io.StringIO()):
                code = run_notebook.main(['--method', 'raw', '--task-manifest', str(manifest), '--output-root', str(root / 'out'), '--', '--provider', 'deepseek'])
            self.assertEqual(code, 0)
            state = json.loads((root / 'out/one/status.json').read_text())
            self.assertEqual(state['status'], 'completed')
            self.assertFalse(state['agent_succeeded'])


if __name__ == '__main__':
    unittest.main()
