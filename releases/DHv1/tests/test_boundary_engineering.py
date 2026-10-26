"""Regress six second-pass defects without changing exploration policy or calling API."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests'),str(ROOT/'audit')]
import deep_engineering_audit as probes
from bestfgs.expectation import prepare, observe, evaluate
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_memory import action_key
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import CommandSpec, CommandResult, ModelCallError, TaskSpec
from bestfgs.retrac_adapter import (OpenAICompatibleJSONClient, RetracModelConfig,
                                    _request_bytes_worker, _request_bytes_with_hard_timeout)
from bestfgs.tool_outcomes import assess
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT, memory_response

# Unit-test the transport's clock projection with its actual HTTP worker mocked.
# The acceptance harness still blocks ordinary client dispatch. Capturing this
# implementation lets this one pure unit test inspect it without opening HTTP.
REQUEST_BYTES_IMPLEMENTATION = OpenAICompatibleJSONClient._request_bytes


def envelope(value):
    return json.dumps(dict(choices=[dict(message=dict(content=value),finish_reason='stop')])).encode()


def sleeping_request_fixture(send,*args):
    """Spawnable pure sleep, never HTTP, to test a real request worker kill."""
    time.sleep(5)


class FeedbackBoundaryTests(unittest.TestCase):
    def test_blocked_history_reports_no_execution_not_old_evidence(self):
        report = probes.blocked_history()
        self.assertFalse(report['reproduced'])
        self.assertTrue(report['blocked_turn_feedback']['not_executed'])
        self.assertTrue(report['blocked_turn_feedback']['cached_result_is_historical'])
        self.assertNotIn('evidence',report['blocked_turn_feedback'])
        self.assertEqual(report['actual_tool_calls'],1)

    def test_cached_result_keeps_its_original_evidence_id(self):
        feedback = probes.blocked_history()['blocked_turn_feedback']
        self.assertEqual(feedback['action_loop']['prior_result']['id'],'E1')

    def test_one_declared_retry_still_executes_then_blocks_again(self):
        action = run_action('read','config.txt')
        retry = dict(action,loop_retry=dict(reason='External state may have changed',
                                           expected_change='A different diagnostic output'))
        result,_,runner,_ = probes.exercise([action,retry,action,SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],2)
        self.assertEqual(result['mechanism_utilization']['action_loop_blocks'],1)
        self.assertIn('evidence',runner.conversation.turns[1]['feedback'])
        self.assertTrue(runner.conversation.turns[2]['feedback']['not_executed'])

    def test_blocked_memory_does_not_credit_next_unrelated_tool(self):
        report = probes.blocked_memory_chain()
        self.assertFalse(report['reproduced'])
        self.assertEqual(len(report['followups']),1)
        self.assertFalse(report['followups'][0]['outcome_observed'])
        self.assertTrue(report['followups'][0]['not_executed'])
        counts = report['mechanism_utilization']
        self.assertEqual(counts['memory_followup_runs'],0)
        self.assertEqual(counts['memory_followup_succeeded'],0)
        self.assertEqual(counts['memory_followup_workspace_changed'],0)
        self.assertEqual(counts['memory_followup_not_executed'],1)

    def test_mismatching_actual_command_is_not_credited(self):
        runner = object.__new__(LeanTaskRunner)
        runner.counts = Counter(); events = []
        runner._emit = lambda event,**fields:events.append((event,fields))
        runner.pending_memory_outcome = dict(expected_command_key=action_key(run_action('read')),
            intervention_id='MI1',memory_ids=['M1'],revised_action=run_action('read'))
        runner._consume_memory_followup('run',outcome_observed=True,succeeded=True,
            workspace_changed=True,command_key=action_key(run_action('write','unrelated')))
        self.assertIsNone(runner.pending_memory_outcome)
        self.assertEqual(runner.counts['memory_followup_mismatches'],1)
        self.assertEqual(runner.counts['memory_followup_succeeded'],0)
        self.assertEqual(runner.counts['memory_followup_runs'],0)
        self.assertEqual(events[0][0],'memory_followup_mismatch')

    def test_executor_exception_closes_memory_chain(self):
        class Environment(FakeEnvironment):
            def execute(self,action,deadline):
                if action['argv'][0]=='bad-executor':
                    raise ValueError('synthetic executor error')
                return super().execute(action,deadline)
        env = Environment(); env.dependencies['config.txt']='file:v1'
        memory = dict(kind='finding',conclusion='Config test was observed',condition='config unchanged',
                      targets=['config.txt'],evidence_ids=['E1'])
        actions = [run_action('read','config.txt'),
            dict(action='checkpoint',label='retain',hypothesis='observed config',memory=memory),
            memory_response(run_action('bad-executor',uses_memory=['M1'],memory_reason='Read prior config')),
            memory_response(run_action('write','unrelated')),memory_response(SUBMIT)]
        result,events,_,_ = probes.exercise(actions,env)
        chains = [e for e in events if e['event']=='memory_followup_outcome']
        self.assertEqual(len(chains),1)
        self.assertEqual(chains[0]['reason'],'executor_result_unavailable')
        self.assertFalse(chains[0]['outcome_observed'])
        self.assertEqual(result['mechanism_utilization']['memory_followup_succeeded'],0)


class ActionMetricTests(unittest.TestCase):
    def test_purpose_only_change_is_not_executable_change(self):
        self.assertFalse(probes.purpose_only_change()['reproduced'])

    def reconsider(self,original,revised):
        runner = object.__new__(LeanTaskRunner)
        runner.counts = Counter(); runner._emit = lambda *args,**kwargs:None
        runner.pending_memory_proposal = dict(id='MI1',matched_memories=[dict(id='M1')],
                                             proposed_action=runner._action_core(original))
        runner._record_memory_reconsideration(revised)
        return runner

    def test_purpose_and_timeout_and_retry_claim_do_not_credit_change(self):
        action = run_action('cat','config.txt')
        revised = dict(action,purpose='New strategy claim',timeout_seconds=120,
                       loop_retry={'reason':'External change','expected_change':'new output'})
        runner = self.reconsider(action,revised)
        self.assertEqual(runner.counts['memory_action_changed'],0)
        self.assertEqual(runner.counts['memory_action_unchanged'],1)

    def test_normalized_shell_spacing_is_not_credited_as_change(self):
        runner = self.reconsider(run_action('bash','-lc','cat config.txt'),
                                run_action('bash','-lc','cat   config.txt'))
        self.assertEqual(runner.counts['memory_action_changed'],0)

    def test_argv_cwd_and_stdin_changes_are_credited(self):
        original = run_action('cat','config.txt')
        for revised in (run_action('cat','other.txt'),dict(original,cwd='sub'),dict(original,stdin='data')):
            with self.subTest(revised=revised):
                self.assertEqual(self.reconsider(original,revised).counts['memory_action_changed'],1)


class DeadlineBoundaryTests(unittest.TestCase):
    def client(self):
        return OpenAICompatibleJSONClient(RetracModelConfig('fixture','https://invalid.example','fake-key',
            timeout_seconds=3,max_wall_time_seconds=3,request_attempts=2,retry_interval_seconds=2,
            max_retry_interval_seconds=2))

    def test_task_expiry_prevents_second_wire_attempt(self):
        report = probes.deadline_retry()
        self.assertFalse(report['reproduced'])
        self.assertEqual(report['simulated_wire_attempts'],1)
        self.assertLessEqual(report['measured_simulated_wall_seconds'],3)
        self.assertEqual(report['stop_reason'],'wall_budget')

    def test_valid_retry_with_time_remaining_is_preserved(self):
        client = self.client(); client.request_deadline = 10
        clock = [0.0]
        def request(**kwargs):
            clock[0] += 2.5
            return envelope('{broken' if client.api_request_count==1 else '{"ok":true}')
        with patch('bestfgs.retrac_adapter.time.monotonic',side_effect=lambda:clock[0]), \
             patch('bestfgs.retrac_adapter.time.sleep',side_effect=lambda delay:clock.__setitem__(0,clock[0]+delay)), \
             patch.object(OpenAICompatibleJSONClient,'_request_bytes',side_effect=request):
            self.assertEqual(client.complete_json(system_prompt='fixture',user_prompt='fixture'),{'ok':True})
        self.assertEqual(client.api_request_count,2)
        self.assertEqual(clock[0],7)

    def test_unset_deadline_preserves_legacy_per_attempt_policy(self):
        client = self.client()
        with patch.object(OpenAICompatibleJSONClient,'_request_bytes',side_effect=[
                envelope('{broken'),envelope('{"ok":true}')]), \
             patch('bestfgs.retrac_adapter.time.sleep'):
            self.assertEqual(client.complete_json(system_prompt='fixture',user_prompt='fixture'),{'ok':True})
        self.assertIsNone(client.request_deadline)
        self.assertEqual(client.api_request_count,2)

    def test_expired_deadline_dispatches_zero_requests(self):
        client = self.client(); client.request_deadline = 1
        with patch('bestfgs.retrac_adapter.time.monotonic',return_value=2), \
             patch.object(OpenAICompatibleJSONClient,'_request_bytes') as request:
            with self.assertRaises(ModelCallError):
                client.complete_json(system_prompt='fixture',user_prompt='fixture')
            request.assert_not_called()
        self.assertEqual(client.api_request_count,0)

    def test_remaining_fraction_reaches_killable_transport_worker(self):
        client = self.client(); client.request_deadline = 10
        with patch('bestfgs.retrac_adapter.time.monotonic',return_value=8.75), \
             patch('bestfgs.retrac_adapter._request_bytes_with_hard_timeout',return_value=b'fixture') as request:
            REQUEST_BYTES_IMPLEMENTATION(client,endpoint='https://invalid.example',encoded=b'{}',headers={})
        self.assertEqual(request.call_args.kwargs['timeout_seconds'],1.25)
        self.assertEqual(request.call_args.kwargs['max_wall_time_seconds'],1.25)
        self.assertEqual(request.call_args.kwargs['absolute_deadline'],10)

    def test_expired_child_does_not_open_http_connection(self):
        send = Mock()
        with patch('bestfgs.retrac_adapter.time.monotonic',return_value=3), \
             patch('bestfgs.retrac_adapter.urllib.request.urlopen') as request:
            _request_bytes_worker(send,'https://invalid.example',b'{}',{},1,False,absolute_deadline=2)
        request.assert_not_called()
        self.assertEqual(send.send.call_args.args[0][0:2],('error','TimeoutError'))
        send.close.assert_called_once()

    def test_task_controller_restores_existing_client_deadline(self):
        client = self.client(); client.request_deadline = 99
        original = client.config
        seen = []
        def request(**kwargs):
            seen.append(client.request_deadline)
            return envelope(json.dumps(SUBMIT))
        with tempfile.TemporaryDirectory() as tmp, \
             patch('bestfgs.lean_runtime.time.monotonic',return_value=0), \
             patch.object(OpenAICompatibleJSONClient,'_request_bytes',side_effect=request):
            result = LeanTaskRunner(FakeEnvironment(),client,Scripted([]),
                probes.config(max_turns=1,wall_seconds=3),Path(tmp)/'audit').run(TaskSpec('fixture','Submit fixture'))
        self.assertTrue(result['submitted'])
        self.assertEqual(seen,[3])
        self.assertEqual(client.request_deadline,99)
        self.assertIs(client.config,original)


@unittest.skipUnless(os.name=='posix','real Linux filesystem/backend')
class LinuxPathBoundaryTests(unittest.TestCase):
    def test_absolute_deadline_kills_real_sleeping_request_worker(self):
        started = time.monotonic()
        with patch('bestfgs.retrac_adapter._request_bytes_worker',sleeping_request_fixture):
            with self.assertRaises(TimeoutError):
                _request_bytes_with_hard_timeout(endpoint='https://invalid.example',encoded=b'{}',headers={},
                    timeout_seconds=10,max_wall_time_seconds=10,absolute_deadline=started+0.3)
        self.assertLess(time.monotonic()-started,2)

    def test_fallback_reads_actual_workspace(self):
        report = probes.fallback_root()
        self.assertFalse(report['reproduced'])
        self.assertIn('DHV1_ISOLATED_CONFIG_SENTINEL',report['stdout'])
        self.assertEqual(report['return_code'],0)

    def test_parent_symlink_is_unknown_and_cannot_match_expectation(self):
        report = probes.ancestor_symlink()
        self.assertFalse(report['reproduced'])
        self.assertEqual(report['observed_state'],'unknown')
        self.assertEqual(report['expectation_status'],'unknown')

    def test_broken_parent_link_is_not_misreported_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed = root/'seed'; seed.mkdir()
            env = LiveWorkspace(seed,root/'run')
            (env.workspace/'link').symlink_to(root/'absent',target_is_directory=True)
            self.assertEqual(env.dependency_state(['link/file.txt']),{'link/file.txt':'unknown'})

    def test_normal_file_and_absent_file_remain_observable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed = root/'seed'; seed.mkdir()
            (seed/'normal.txt').write_text('valid fixture')
            env = LiveWorkspace(seed,root/'run')
            states = env.dependency_state(['normal.txt','missing.txt'])
            self.assertTrue(states['normal.txt'].startswith('file:'))
            self.assertEqual(states['missing.txt'],'missing')

    def test_direct_symlink_stays_explicit_not_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed = root/'seed'; seed.mkdir()
            (seed/'normal.txt').write_text('valid fixture')
            env = LiveWorkspace(seed,root/'run')
            (env.workspace/'link.txt').symlink_to('normal.txt')
            self.assertEqual(env.dependency_state(['link.txt']),{'link.txt':'link:normal.txt'})


if __name__=='__main__':
    unittest.main()
