"""No Docker/API calls. Exercise the same dispatcher used by the runner."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'deploy/longcli/dispatch_policy.py'
spec = importlib.util.spec_from_file_location('dispatch_policy', path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class DispatchTests(unittest.TestCase):
    def run_rows(self, outcomes):
        calls, snapshots = [], []
        def trial(row):
            calls.append(row['task'])
            return dict(task=row['task'], **outcomes[int(row['task'])])
        result = policy.dispatch_trials([dict(task=str(i)) for i in range(len(outcomes))], trial, snapshots.append, concurrency=1)
        return calls, snapshots, result

    def good(self):
        return dict(state='graded', score=0.0, http_errors=[500], transport_errors=1)

    def isolated(self):
        return dict(state='needs_attention', engineering_fault='tool_json_retries_exhausted',
                    grading_state='complete', container_destroyed=True, score=1.0)

    def test_isolated_pilot_does_not_block_other_tasks_or_replay_itself(self):
        calls, snapshots, result = self.run_rows([self.isolated(), self.good(), self.good()])
        self.assertEqual(calls, ['0', '1', '2'])
        self.assertEqual(result['state'], 'complete_with_errors')
        self.assertEqual(result['pending'], [])
        self.assertEqual(result['results'][0]['state'], 'needs_attention')

    def test_repeated_shared_problem_pauses_new_dispatch(self):
        calls, _, result = self.run_rows([self.isolated(), self.isolated(), self.good()])
        self.assertEqual(calls, ['0', '1'])
        self.assertEqual(result['pending'], ['2'])
        self.assertEqual(result['pause_reason'], 'repeated_tool_json_failures')

    def test_auth_disk_config_grading_and_unknown_still_pause(self):
        for fault in ['provider_request_rejected', 'OSError', 'grading_failed', 'cleanup_unconfirmed', 'native_error_inspect_logs']:
            with self.subTest(fault=fault):
                calls, _, result = self.run_rows([dict(state='needs_attention', engineering_fault=fault, score=1.0), self.good()])
                self.assertEqual(calls, ['0'])
                self.assertEqual(result['state'], 'needs_attention')

    def test_incomplete_grading_or_cleanup_cannot_be_isolated(self):
        for override in [dict(grading_state='failed'), dict(container_destroyed=False)]:
            result = {**self.isolated(), **override}
            self.assertEqual(policy.disposition(result), 'pause')

    def test_recovered_http_errors_are_not_new_failures(self):
        calls, _, result = self.run_rows([self.good(), self.good()])
        self.assertEqual(calls, ['0', '1'])
        self.assertEqual(result['state'], 'complete')

    def test_terminal_marker_requires_actual_final_matching_error(self):
        marker='TOOL_JSON_RECOVERY_EXHAUSTED: native request retry allowance exhausted'
        error='dsh: MALFORMED_RESPONSE: DeepSeek Messages stream: tool input is invalid JSON'
        self.assertEqual(policy.terminal_fault(1, error, recovery_exhausted=True), 'tool_json_retries_exhausted')
        self.assertEqual(policy.terminal_fault(1, error), 'native_error_inspect_logs')
        self.assertEqual(policy.terminal_fault(1, 'dsh: AUTH', recovery_exhausted=True), 'native_error_inspect_logs')
        self.assertIsNone(policy.terminal_fault(0, marker+'\n'+error))
        self.assertEqual(policy.terminal_fault(1, marker+'\n'+error, 'cleanup_unconfirmed'), 'cleanup_unconfirmed')

    def test_duplicate_tasks_are_not_launched(self):
        with self.assertRaises(ValueError):
            policy.dispatch_trials([dict(task='same'), dict(task='same')], lambda _: self.fail('must not run'), lambda _: None)


if __name__ == '__main__':
    unittest.main()
