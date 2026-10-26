"""Counter-only regressions: scripted clients, no API or cloud deployment."""
from collections import Counter
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_audit import read_trace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec
from bestfgs.recovery_clock import recovery_steps
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


class RecoveryCounterTests(unittest.TestCase):
    def exercise(self, actions, *, monitor=False, advisor=(), **options):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        config = dict(max_turns=80, max_tools=30,
            contrastive_mode='orthogonal', memory_reliability=True,
            outcome_reliability=True, memory_decision=False,
            memory_injection=False, diagnostic_advisor_threshold=100,
            repeated_failure_threshold=100)
        config.update(options)
        if monitor:
            config.update(semantic_monitor=True, monitor_reliability=True)
        actor = Scripted(actions)
        guide = Scripted(advisor)
        observer = Scripted([dict(verdict='uncertain', reason='No new evidence',
            evidence_ids=['E1'], next_check='', memories=[])]*20) if monitor else None
        environment = FakeEnvironment()
        runner = LeanTaskRunner(environment, actor, guide, LeanConfig(**config),
            Path(temp.name)/'audit', monitor_client=observer)
        result = runner.run(TaskSpec('counter-fixture', 'Inspect public files'))
        return result, read_trace(Path(temp.name)/'audit/events.jsonl'), runner, environment

    def test_clock_counts_refusals_but_not_internal_model_requests(self):
        counts = Counter(tool_calls=3, action_loop_blocks=7,
            contrastive_rejections=2, model_requests=100, monitor_calls=4,
            advisor_calls=3, protocol_errors=1)
        runner = SimpleNamespace(counts=counts)
        self.assertEqual(recovery_steps(runner), 12)
        self.assertEqual(counts['tool_calls'], 3)
        counts['model_requests'] += 5
        self.assertEqual(recovery_steps(runner), 12)

    def test_without_refusals_clock_is_the_original_tool_clock(self):
        runner = SimpleNamespace(counts=Counter(tool_calls=9))
        self.assertEqual(recovery_steps(runner), 9)

    def test_blocked_successful_reads_advance_monitor_cooldown_and_quota(self):
        action = run_action('read', 'f.py')
        result, events, runner, environment = self.exercise(
            [action]*14+[SUBMIT], monitor=True, max_tools=12,
            monitor_cooldown_tools=2, max_monitor_calls=4)
        reviews = [e for e in events if e['event']=='monitor_review']
        self.assertTrue(result['submitted'], result)
        self.assertGreaterEqual(len(reviews), 2)
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(len(environment.executed), 1)
        self.assertTrue(all(e['reviewed_after_tool']==1 for e in reviews))
        self.assertEqual(runner.last_monitor_tool, 1)
        self.assertGreater(runner.last_monitor_recovery_step, 1)
        self.assertLessEqual(result['mechanism_utilization']['monitor_calls'], 4)
        self.assertEqual(len(runner.evidence), 1)
        self.assertEqual(runner.contrastive_failures, [])

    def test_blocked_actions_advance_advisor_cooldown(self):
        action = run_action('read', 'f.py')
        consult = dict(action='consult', question='Which public file next?')
        result, events, runner, _ = self.exercise(
            [action, consult, action, action, action, consult, consult, SUBMIT],
            advisor=[dict(alternatives=[])]*2, advisor_cooldown_tools=3)
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(result['advisor_rounds'], 2)
        self.assertEqual(runner.last_advisor_tool, 1)
        self.assertEqual(runner.last_advisor_recovery_step, 4)
        self.assertEqual(sum(e['event']=='advisor_skipped' for e in events), 1)

    def test_four_rejected_attempts_can_reactivate_exploration_without_new_tool(self):
        fail = run_action('fail')
        result, events, runner, environment = self.exercise([fail]*18+[SUBMIT])
        starts = [e for e in events if e['event']=='contrastive_episode_start']
        self.assertTrue(result['submitted'], result)
        self.assertGreaterEqual(len(starts), 3)
        self.assertTrue(all(e['trigger']=='unchanged_action_loop' for e in starts))
        self.assertEqual(sum(a['argv'][0]=='fail' for a in environment.executed), 1)
        self.assertEqual(result['tool_calls'], 2)  # failure + first diagnostic only
        self.assertEqual(result['mechanism_utilization']['protocol_errors'], 0)
        self.assertGreater(result['mechanism_utilization']['contrastive_rejections'], 2)
        self.assertEqual(len(runner.evidence), 2)

    def test_actual_tool_budget_is_not_spent_by_refusals(self):
        action = run_action('read', 'f.py')
        result, _, runner, environment = self.exercise(
            [action]*20+[run_action('write', 'fixed'), SUBMIT], max_tools=2)
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 2)
        self.assertEqual(environment.value, 'fixed')
        self.assertEqual(recovery_steps(runner), 21)


if __name__ == '__main__':
    unittest.main()
