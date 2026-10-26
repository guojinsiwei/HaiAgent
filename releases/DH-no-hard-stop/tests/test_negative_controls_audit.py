"""Reproduce unchanged questionable policies, not claims of measured score harm."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.action_loop import ActionLoopGuard
from bestfgs.contrastive_exploration import validate_orthogonal
from bestfgs.error_routing import readonly_action
from bestfgs.memory_injection import validate_review
from test_lean import run_action, SUBMIT
import test_memory_injection as injection_fixtures
from test_contrastive_exploration import orthogonal_action


class NegativeControlsAuditTests(unittest.TestCase):
    def observation(self, **extra):
        return dict(id='E1', before='workspace-A', after='workspace-A', return_code=0,
                    stdout='prior output', stderr='', timed_out=False,
                    capture_incomplete=False, terminal_projection_incomplete=False,
                    relevant_dependencies={}, **extra)

    def test_numeric_parameter_change_is_rejected_as_identical_tfidf(self):
        old = run_action('python', 'train.py', '--lr', '0.1')
        new = orthogonal_action(run_action('python', 'train.py', '--lr', '0.2'))
        audit, reason = validate_orthogonal(new, [{'command':'python train.py --lr 0.1'}], .8)
        self.assertAlmostEqual(audit['max_similarity'], 1.0)
        self.assertEqual(reason, 'command_similarity_above_threshold')
        self.assertNotEqual(old['argv'], new['argv'])

    def test_timeout_change_does_not_allow_reexecution(self):
        guard = ActionLoopGuard()
        old = run_action('make', 'test', timeout_seconds=10)
        row = self.observation()
        row.update(return_code=-1, timed_out=True, stderr='tool deadline')
        guard.observe(old, row)
        blocked = guard.check(dict(old, timeout_seconds=120), 'workspace-A', {})
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked['reason'], 'same_command_in_unchanged_workspace')

    def test_advertised_external_retry_is_not_honored_by_final_guard(self):
        guard = ActionLoopGuard()
        action = run_action('cat', '/tmp/status')
        guard.observe(action, self.observation())
        retry = dict(action, loop_retry={'reason':'external status changed',
                                        'expected_change':'new completion status'})
        self.assertIsNotNone(guard.check(retry, 'workspace-A', {}))

    def test_selected_dependencies_override_changed_whole_workspace(self):
        guard = ActionLoopGuard()
        action = run_action('python', 'main.py')
        row = self.observation()
        row.update(relevant_dependencies={'main.py':'file:same'},
                   dependency_before={'main.py':'file:same'})
        guard.observe(action, row)
        # A changed but untracked imported file cannot invalidate this cache.
        self.assertIsNotNone(guard.check(action, 'workspace-B', {'main.py':'file:same'}))

    def test_review_key_order_rejects_identical_structured_contents(self):
        good = injection_fixtures.review(run_action('write', 'fixed'))
        validate_review(good, {'M1'}, True)
        reordered = dict(action=good['action'], argv=good['argv'],
                         memory_review=good['memory_review'],
                         strategy_adjustment=good['strategy_adjustment'])
        with self.assertRaisesRegex(ValueError, 'first three keys'):
            validate_review(reordered, {'M1'}, True)

    def test_three_review_order_errors_stop_before_valid_repair(self):
        good = injection_fixtures.review(run_action('write', 'fixed'))
        wrong = dict(action=good['action'], argv=good['argv'],
                     memory_review=good['memory_review'],
                     strategy_adjustment=good['strategy_adjustment'])
        result, runner, actor, events = injection_fixtures.InjectionTests.exercise(self,
            [run_action('fail'), run_action('fail'), wrong, wrong, wrong, good,
             injection_fixtures.review(SUBMIT)])
        self.assertEqual(result['stop_reason'], 'model_or_protocol_error_limit')
        self.assertFalse(result['submitted'])
        self.assertEqual(result['mechanism_utilization']['protocol_errors'], 3)
        self.assertFalse(any(a['argv'][0]=='write' for a in runner.environment.executed))

    def test_common_readonly_probes_do_not_get_reconnaissance_exemption(self):
        for argv in (['git', 'diff'], ['bash', '-c', 'cat config.json && ls'],
                     ['python', '-c', 'print(1)']):
            self.assertFalse(readonly_action(run_action(*argv)))


if __name__ == '__main__':
    unittest.main()
