"""Expectation-only regressions: scripted models, no network or paid calls."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.expectation import prepare, observe, evaluate, EXPECTATION_INSTRUCTION
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import CommandResult, CommandSpec, TaskSpec
from bestfgs.tool_outcomes import assess
from bestfgs.action_loop import ActionLoopGuard
from test_lean import Scripted, FakeEnvironment, run_action, SUBMIT


def review(spec, action=None, result=None, before=None, after=None, **kwargs):
    action = action or run_action('make')
    result = result or CommandResult(CommandSpec(tuple(action['argv']), 'fixture'), 0, '', '', 0)
    return evaluate(prepare(spec), action, result, assess(result), before, after,
                    result.stdout, result.stderr, **kwargs)


class ContractTests(unittest.TestCase):
    def test_missing_is_nonfatal_unknown(self):
        self.assertEqual(prepare(None)['contract_status'], 'missing')
        self.assertEqual(review(None)['status'], 'unknown')

    def test_bad_contracts_are_nonfatal_unknown(self):
        for spec in ['ok', {}, {'kind':'success'}, {'kind':'public_test','status':'great'},
                     {'kind':'unknown','reason':''}, {'kind':'file_state','path':'x','state':'file','changed':1}]:
            with self.subTest(spec=spec):
                self.assertEqual(prepare(spec)['contract_status'], 'invalid')
                self.assertEqual(review(spec)['status'], 'unknown')

    def test_unsafe_paths_are_never_inspected(self):
        env = Mock()
        for path in ['/etc/passwd', '../secret', '/app/../secret', '$OUT', '.git/config', 'tests/hidden.py']:
            spec = prepare(dict(kind='file_state', path=path, state='file'))
            self.assertEqual(spec['contract_status'], 'invalid')
            self.assertEqual(observe(env, spec), {})
        env.dependency_state.assert_not_called()

    def test_task_root_relative_coordinates(self):
        contract = prepare(dict(kind='build', artifact='/app/cow/kernel/kernel'))
        self.assertEqual(contract['artifact'], 'cow/kernel/kernel')

    def test_absence_only_and_overlapping_markers_are_invalid(self):
        for spec in [dict(kind='output', not_contains='ModuleNotFoundError'),
                     dict(kind='output', contains='ok', not_contains='not ok')]:
            self.assertEqual(prepare(spec)['contract_status'], 'invalid')

    def test_observe_reuses_known_values_without_task_command(self):
        env = Mock()
        spec = prepare(dict(kind='build', artifact='cow/kernel/kernel'))
        self.assertEqual(observe(env, spec, {'cow/kernel/kernel':'missing'}), {'cow/kernel/kernel':'missing'})
        env.dependency_state.assert_not_called()
        env.execute.assert_not_called()

    def test_inspection_failure_is_unknown_not_exception(self):
        env = Mock(); env.dependency_state.side_effect = RuntimeError('unavailable')
        spec = prepare(dict(kind='build', artifact='cow/kernel/kernel'))
        self.assertEqual(observe(env, spec), {'cow/kernel/kernel':'unknown'})
        env.execute.assert_not_called()

    def test_enable_flag_is_strict_boolean(self):
        with self.assertRaises(ValueError): LeanConfig(expectation_enabled=1)


class OutputTests(unittest.TestCase):
    def result(self, **changes):
        return replace(CommandResult(CommandSpec(('python3','probe.py'), 'fixture'),
                       0, 'version=3', '', 0), **changes)

    def test_concrete_marker_matches_without_claiming_success(self):
        r = review(dict(kind='output', stream='stdout', contains='version=3'), result=self.result())
        self.assertEqual(r['status'], 'matched')
        self.assertIsNone(r['task_success']); self.assertIsNone(r['local_progress'])
        self.assertFalse(r['automatic_checkpoint']); self.assertFalse(r['route_invalidated'])

    def test_missing_marker_is_local_contradiction(self):
        r = review(dict(kind='output', contains='version=4'), result=self.result())
        self.assertEqual(r['status'], 'contradicted')
        self.assertFalse(r['route_invalidated'])

    def test_conflicting_output_is_unknown(self):
        r = review(dict(kind='output', contains='READY', not_contains='FAILED'),
                   result=self.result(stdout='READY\nFAILED'))
        self.assertEqual(r['status'], 'unknown')

    def test_partial_execution_or_capture_is_never_match(self):
        spec = dict(kind='output', contains='version=3')
        for changes in [dict(timed_out=True), dict(blocked=True), dict(output_truncated=True),
                        dict(execution_observation=dict(coverage='top_level_bash_only',complete=False))]:
            with self.subTest(changes=changes):
                self.assertEqual(review(spec, result=self.result(**changes))['status'], 'unknown')
        self.assertEqual(review(spec, result=self.result(), terminal_incomplete=True)['status'], 'unknown')

    def test_error_output_can_be_observed_without_becoming_repair_success(self):
        r = review(dict(kind='output', stream='stderr', contains='ModuleNotFoundError'),
                   result=self.result(return_code=1,stdout='',stderr='ModuleNotFoundError: missing'))
        self.assertEqual(r['status'], 'matched'); self.assertIsNone(r['local_progress'])
        self.assertIsNone(r['task_success'])


class StateTests(unittest.TestCase):
    path = 'cow/kernel/kernel'

    def test_clean_build_and_changed_artifact_match_locally(self):
        r = review(dict(kind='build',artifact=self.path),
                   action=run_action('bash','-lc','cd cow && make'),
                   before={self.path:'missing'}, after={self.path:'file:binary-hash'})
        self.assertEqual(r['status'], 'matched'); self.assertTrue(r['local_progress'])
        self.assertIsNone(r['task_success']); self.assertFalse(r['automatic_checkpoint'])

    def test_build_failure_cannot_be_saved_by_existing_artifact(self):
        result = CommandResult(CommandSpec(('make',), 'fixture'), 2, '', 'compiler error', 0)
        r = review(dict(kind='build',artifact=self.path), result=result,
                   before={self.path:'missing'},after={self.path:'file:binary-hash'})
        self.assertEqual(r['status'], 'contradicted')

    def test_stale_artifact_does_not_prove_new_build(self):
        r = review(dict(kind='build',artifact=self.path),
                   before={self.path:'file:same'},after={self.path:'file:same'})
        self.assertEqual(r['status'], 'unknown')

    def test_failed_pipeline_stage_cannot_be_saved_by_exit_zero(self):
        result = CommandResult(CommandSpec(('bash','-lc','make | tail'), 'fixture'), 0, '', '', 0,
                               execution_observation={'nonzero_statuses':[2]})
        r = review(dict(kind='build',artifact=self.path),
                   action=run_action('bash','-lc','make | tail'),result=result,
                   before={self.path:'missing'},after={self.path:'file:new'})
        self.assertEqual(r['status'], 'contradicted')

    def test_touch_is_not_a_recognized_build(self):
        r = review(dict(kind='build',artifact=self.path), action=run_action('touch',self.path),
                   before={self.path:'missing'},after={self.path:'file:new'})
        self.assertEqual(r['status'], 'unknown')

    def test_missing_artifact_is_contradiction(self):
        r = review(dict(kind='build',artifact=self.path),
                   before={self.path:'missing'},after={self.path:'missing'})
        self.assertEqual(r['status'], 'contradicted')

    def test_requested_file_change_is_checked(self):
        spec = dict(kind='file_state',path='output.txt',state='file',changed=True)
        r = review(spec,before={'output.txt':'missing'},after={'output.txt':'file:new'})
        self.assertEqual(r['status'], 'matched'); self.assertIsNone(r['local_progress'])
        self.assertEqual(review(spec,before={'output.txt':'file:old'},
                         after={'output.txt':'file:old'})['status'], 'contradicted')

    def test_unknown_or_symlink_state_is_not_guessed(self):
        spec = dict(kind='file_state',path='output.txt',state='file',changed=True)
        for value in ['unknown','link:elsewhere']:
            self.assertEqual(review(spec,before={'output.txt':'missing'},
                             after={'output.txt':value})['status'], 'unknown')


class PublicTestTests(unittest.TestCase):
    def test_supported_pytest_pass_and_failure(self):
        for code, output, expected in [(0,'=== 4 passed in 0.1s ===','matched'),
                                       (1,'=== 1 failed, 3 passed in 0.1s ===','contradicted')]:
            result = CommandResult(CommandSpec(('pytest','test_public.py'), 'fixture'),code,output,'',0)
            r = review(dict(kind='public_test',status='passed'),result=result)
            self.assertEqual(r['status'], expected); self.assertIsNone(r['task_success'])
        result = CommandResult(CommandSpec(('pytest','test_public.py'), 'fixture'),
                               1,'=== 1 failed in 0.1s ===','',0)
        self.assertEqual(review(dict(kind='public_test',status='failed'),result=result)['status'], 'matched')

    def test_echoed_summary_or_unrecognized_test_is_unknown(self):
        result = CommandResult(CommandSpec(('echo','=== 4 passed in 0.1s ==='), 'fixture'),
                               0,'=== 4 passed in 0.1s ===','',0)
        self.assertEqual(review(dict(kind='public_test',status='passed'),result=result)['status'], 'unknown')


class RuntimeTests(unittest.TestCase):
    def run_case(self, actions, *, enabled=True):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        environment = FakeEnvironment()
        class Capture(Scripted):
            systems = []
            def complete_json(self, **kwargs):
                self.systems.append(kwargs['system_prompt'])
                return super().complete_json(**kwargs)
        actor = Capture(actions); actor.systems = []
        runner = LeanTaskRunner(environment,actor,Scripted([]),
            LeanConfig(max_turns=len(actions),max_tools=10,max_consecutive_errors=1,
                       expectation_enabled=enabled),Path(tmp.name)/'trace')
        result = runner.run(TaskSpec('fixture','Complete the public task'))
        events = read_trace(Path(tmp.name)/'trace/events.jsonl')
        return result,events,environment,actor

    def test_register_before_execution_and_return_review_without_extra_rounds(self):
        action = run_action('artifact','output.txt','newhash',
            expected_observation=dict(kind='file_state',path='output.txt',state='file',changed=True))
        result,events,env,actor = self.run_case([action,SUBMIT])
        self.assertEqual(result['version'],'DHv1')
        self.assertEqual(next(e for e in events if e['event']=='header')['version'],'DHv1')
        self.assertTrue(result['submitted']); self.assertEqual(result['interaction_rounds'],2)
        self.assertEqual(result['tool_calls'],1); self.assertEqual(len(env.executed),1)
        self.assertEqual(result['mechanism_utilization']['expectations_matched'],1)
        order = [e['event'] for e in events]
        self.assertLess(order.index('expectation_registered'),order.index('tool_attempt'))
        self.assertLess(order.index('tool_attempt'),order.index('expectation_outcome'))
        outcome = next(e for e in events if e['event']=='expectation_outcome')
        self.assertEqual(outcome['status'],'matched'); self.assertEqual(outcome['evidence_id'],'E1')
        evidence = actor.prompts[1]['fixed_context']['evidence']
        self.assertEqual(evidence[-1]['expectation']['status'],'matched')
        self.assertIn(EXPECTATION_INSTRUCTION,actor.systems[0])

    def test_missing_or_invalid_expectation_does_not_consume_protocol_retries(self):
        for spec in [None, 'not an object']:
            action = run_action('read',expected_observation=spec)
            result,events,env,_ = self.run_case([action,SUBMIT])
            self.assertTrue(result['submitted']); self.assertEqual(result['tool_calls'],1)
            self.assertEqual(result['mechanism_utilization']['protocol_errors'],0)
            self.assertEqual(result['mechanism_utilization']['expectations_unknown'],1)
            self.assertEqual(len(env.saved),1)  # Existing initial checkpoint only.

    def test_mismatch_does_not_change_stop_policy_or_invalidate_route(self):
        action = run_action('read',expected_observation=dict(kind='output',contains='not-in-output'))
        result,events,env,_ = self.run_case([action,SUBMIT])
        self.assertEqual(result['stop_reason'],'model_submit')
        self.assertEqual(result['mechanism_utilization']['expectations_contradicted'],1)
        self.assertEqual(result['mechanism_utilization']['branch_restores'],0)
        self.assertEqual(len(env.executed),1)

    def test_disabled_mode_has_no_expectation_prompt_inspection_or_metrics(self):
        result,events,env,actor = self.run_case([run_action('read'),SUBMIT],enabled=False)
        self.assertTrue(result['submitted'])
        self.assertNotIn(EXPECTATION_INSTRUCTION,actor.systems[0])
        self.assertFalse(any(e['event'].startswith('expectation_') for e in events))
        self.assertNotIn('expectations_registered',result['mechanism_utilization'])

    def test_expectation_text_cannot_bypass_existing_repeat_guard(self):
        guard = ActionLoopGuard(); action = run_action('cat','file.txt')
        row = dict(id='E1',before='same',after='same',return_code=0,stdout='data',stderr='',
                   timed_out=False,capture_incomplete=False,terminal_projection_incomplete=False)
        guard.observe(action,row)
        alternate = dict(action,expected_observation=dict(kind='output',contains='something novel'))
        self.assertIsNotNone(guard.check(alternate,'same'))


if __name__ == '__main__':
    unittest.main()
