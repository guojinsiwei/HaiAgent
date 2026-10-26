"""Replay the five real failure inputs without a model API or task commands."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_protocol import LeanConfig, parse_action
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.lean_docker import DEPENDENCY_SCRIPT
from bestfgs.memory_events import dependency_paths
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment, Scripted, SUBMIT, run_action

FAILURES = json.loads((ROOT/'tests/v6_failure_responses.json').read_text(encoding='utf-8'))


class EngineeringRepairTests(unittest.TestCase):
    def exercise(self, actions, environment=None):
        with tempfile.TemporaryDirectory() as tmp:
            env = environment or FakeEnvironment()
            actor = Scripted(actions)
            cfg = LeanConfig(max_turns=30, max_tools=20, max_advisor_calls=0,
                             memory_reliability=True, outcome_reliability=True,
                             stagnation_control=True)
            runner = LeanTaskRunner(env, actor, Scripted([]), cfg, Path(tmp)/'audit')
            result = runner.run(TaskSpec('fixture', 'Create useful output'))
            return result, read_trace(Path(tmp)/'audit/events.jsonl'), env, actor

    def test_four_captured_nested_responses_recover_without_execution(self):
        for failure in FAILURES:
            if failure['error'] != 'TypeError':
                continue
            with self.subTest(job=failure['job']):
                raw = failure['last_response']
                with self.assertRaisesRegex(ValueError, 'top level'):
                    parse_action(raw)
                corrected = run_action('write', 'corrected', recovery_plan=dict(
                    hypothesis='Check a corrected action after malformed output', mode='diagnose', targets=[],
                    action_argv=['write', 'corrected'], verification_argv=['read'], success_contains='corrected'))
                result, events, env, actor = self.exercise(
                    [run_action('read')]*3 + [raw, corrected, run_action('read'), SUBMIT])
                self.assertIsNone(result['error_type'])
                self.assertTrue(result['submitted'])
                self.assertEqual(result['mechanism_utilization']['protocol_errors'], 1)
                self.assertEqual(env.value, 'corrected')
                self.assertFalse(any(a['argv'] == raw['action']['argv'] for a in env.executed))
                self.assertTrue(any(e['event'] == 'protocol_error' for e in events))
                self.assertIn('top level', actor.prompts[4]['fixed_context']['feedback']['protocol_error'])

    def test_unhashable_action_values_are_protocol_errors(self):
        for value in ({}, [], ['run'], None, 1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_action(dict(action=value))

    def test_repeated_malformed_actions_stop_as_protocol_not_infrastructure(self):
        result, events, env, actor = self.exercise([dict(action={})]*3 + [SUBMIT])
        self.assertEqual(result['stop_reason'], 'model_or_protocol_error_limit')
        self.assertIsNone(result['error_type'])
        self.assertEqual(result['tool_calls'], 0)
        self.assertFalse(any(e['event'] == 'infrastructure_error' for e in events))

    def test_great_expectations_code_is_not_a_filename(self):
        failure = next(r for r in FAILURES if r['error'] == 'RuntimeError')
        paths = dependency_paths(failure['last_response'])
        self.assertEqual(paths, ['src/dq_audit/audit.py'])
        self.assertEqual(dependency_paths(run_action('bash', '-lc',
                         'python -m example.cli --manifest=configs/public.yml --out outputs/result.json')),
                         ['example.cli', 'configs/public.yml', 'outputs/result.json'])
        self.assertEqual(dependency_paths(run_action('cat', 'x'*300+'.py')), [])
        # Explicit tracked targets still support spaces; inference is conservative.
        self.assertEqual(dependency_paths(run_action('read'), ['my file.py']), ['my file.py'])

    def test_dependency_probe_treats_os_errors_as_unknown_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = DEPENDENCY_SCRIPT.replace("os.path.join('/app',", "os.path.join("+repr(tmp)+",")
            Path(tmp, 'valid.txt').write_text('ok')
            Path(tmp, 'regular.txt').write_text('file, not a directory')
            names = ['x'*300+'.py', 'regular.txt/child.txt', 'missing.txt', 'valid.txt']
            proc = subprocess.run([sys.executable, '-B', '-c', script], input=json.dumps(names),
                                  text=True, capture_output=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            states = json.loads(proc.stdout)
            self.assertEqual(states[names[0]], 'unknown')
            self.assertEqual(states[names[1]], 'missing' if os.name == 'nt' else 'unknown')
            self.assertEqual(states['missing.txt'], 'missing')
            self.assertTrue(states['valid.txt'].startswith('file:2:'))

    def test_actual_infrastructure_failure_has_location_without_exception_data(self):
        class Broken(FakeEnvironment):
            def execute(self, action, deadline):
                raise RuntimeError('sensitive exception data')
        result, events, _, _ = self.exercise([run_action('read')], Broken())
        self.assertEqual(result['stop_reason'], 'infrastructure_error')
        event = next(e for e in events if e['event'] == 'infrastructure_error')
        self.assertEqual(event['error_frames'][-1]['function'], 'execute')
        self.assertTrue(event['error_frames'][-1]['line'] > 0)
        self.assertNotIn('sensitive exception data', json.dumps(event))


if __name__ == '__main__':
    unittest.main()
