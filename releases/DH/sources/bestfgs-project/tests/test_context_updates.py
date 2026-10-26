import copy
from dataclasses import replace
import unittest

from bestfgs.context_updates import merge_pending_context
from bestfgs.models import StructuredContext, TaskSpec
from bestfgs.prompt_views import allocate_stream_budgets, observation_sources, compact
import test_prompt_views as views
import test_collaboration as collaboration
from examples.demo_counter import CounterEnvironment

class ContextUpdateTests(unittest.TestCase):
    def setUp(self):
        self.previous = StructuredContext(task_goal='repair', unresolved_issues=('database down', 'unseen old issue'),
            incomplete_plans=('start database',), analysis_and_conclusions=('connection refused earlier',))
        self.outcome = views.PromptViewTests().outcome('database ready\n')
        self.change = {'field': 'unresolved_issues', 'item': 'database down', 'status': 'resolved',
                       'source_channel': 'command', 'source_index': 0, 'evidence_quote': 'database ready',
                       'reason': 'The readiness check reports the database is available'}

    def test_empty_model_lists_do_not_erase_unseen_items(self):
        merged = merge_pending_context(self.previous, {'unresolved_issues': [], 'incomplete_plans': [],
            'analysis_and_conclusions': []}, [], self.outcome)
        self.assertEqual(merged['unresolved_issues'], list(self.previous.unresolved_issues))
        self.assertEqual(merged['incomplete_plans'], ['start database'])
        self.assertEqual(merged['analysis_and_conclusions'], ['connection refused earlier'])

    def test_additions_are_merged_and_deduplicated(self):
        merged = merge_pending_context(self.previous, {'unresolved_issues': ['new issue', 'database down']}, [], self.outcome)
        self.assertEqual(merged['unresolved_issues'], ['database down', 'unseen old issue', 'new issue'])

    def test_explicit_resolution_requires_evidence_and_keeps_audit(self):
        merged = merge_pending_context(self.previous, {}, [self.change], self.outcome)
        self.assertEqual(merged['unresolved_issues'], ['unseen old issue'])
        self.assertIn('database ready', merged['analysis_and_conclusions'][-1])
        self.assertEqual(self.previous.unresolved_issues, ('database down', 'unseen old issue'))

    def test_invalidated_plan_can_be_replaced(self):
        change = dict(self.change, field='incomplete_plans', item='start database', status='invalidated')
        merged = merge_pending_context(self.previous, {'incomplete_plans': ['start database', 'test application']}, [change], self.outcome)
        self.assertEqual(merged['incomplete_plans'], ['test application'])

    def test_bad_sources_quotes_and_fields_rejected(self):
        for changes in (dict(source_index=9), dict(source_index=True), dict(evidence_quote='fabricated'),
                        dict(field='facts_and_evidence'), dict(item='not an old issue'), dict(reason=''),
                        dict(source_channel='unknown'), dict(status='delete')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                merge_pending_context(self.previous, {}, [dict(self.change, **changes)], self.outcome)

    def test_incomplete_results_cannot_retire_items(self):
        for field in ('timed_out', 'blocked', 'output_truncated'):
            result = replace(self.outcome.command_results[0], **{field: True})
            with self.subTest(field=field), self.assertRaises(ValueError):
                merge_pending_context(self.previous, {}, [self.change], replace(self.outcome, command_results=(result,)))

    def test_memory_role_handoff_preserves_unmentioned_items(self):
        fixture = collaboration.CollaborationTests()
        policy, clients = fixture.make()
        task = TaskSpec('counter-task', 'Reach 3', success_criteria=('counter=3',))
        previous = StructuredContext(task_goal=task.goal, unresolved_issues=('OLD_UNSEEN',), incomplete_plans=('OLD_PLAN',))
        plan = policy.propose_initial_plan(task=task, context=previous, rules=(), limit=1)
        env = CounterEnvironment()
        outcome = env.execute(env.initial_snapshot(), plan.bootstrap_action, 4)
        result = policy.update_transition(task=task, previous=previous, action=plan.bootstrap_action, outcome=outcome)
        self.assertIn('OLD_UNSEEN', result.next_context.unresolved_issues)
        self.assertIn('OLD_PLAN', result.next_context.incomplete_plans)
        self.assertIn('[] means no additions', clients['memory'].prompts[0])

    def test_memory_role_explicit_retirement_reaches_parser(self):
        response = copy.deepcopy(collaboration.MEMORY)
        response['context_changes'] = [dict(self.change, item='counter not checked', evidence_quote='1', reason='counter returned 1')]
        policy, clients = collaboration.CollaborationTests().make(memory=[response])
        task = TaskSpec('counter-task', 'Reach 3')
        previous = StructuredContext(task_goal=task.goal, unresolved_issues=('counter not checked', 'keep me'))
        plan = policy.propose_initial_plan(task=task, context=previous, rules=(), limit=1)
        env = CounterEnvironment()
        outcome = env.execute(env.initial_snapshot(), plan.bootstrap_action, 4)
        result = policy.update_transition(task=task, previous=previous, action=plan.bootstrap_action, outcome=outcome)
        self.assertNotIn('counter not checked', result.next_context.unresolved_issues)
        self.assertIn('keep me', result.next_context.unresolved_issues)
        self.assertEqual([len(c.prompts) for c in clients.values()], [1, 1, 1])

class AllocationTests(unittest.TestCase):
    def test_empty_stream_gets_nothing(self):
        self.assertEqual(allocate_stream_budgets([2000, 0], [1, 3], 1000), [1000, 0])

    def test_short_error_releases_unused_quota(self):
        self.assertEqual(allocate_stream_budgets([2000, 20], [1, 3], 1000), [980, 20])

    def test_error_has_priority_without_starving_stdout(self):
        normal, error = allocate_stream_budgets([3000, 3000], [1, 3], 1000)
        self.assertGreater(error, normal)
        self.assertGreater(normal, 0)
        self.assertEqual(normal + error, 1000)

    def test_never_overallocates(self):
        for budget in (0, 1, 2, 10, 501, 1000, 10000):
            costs = [0, 7, 999, 45]
            result = allocate_stream_budgets(costs, [1, 3, 1, 3], budget)
            self.assertEqual(sum(result), min(budget, sum(costs)))
            self.assertTrue(all(0 <= x <= cap for x, cap in zip(result, costs)))

    def test_actual_nonempty_stdout_uses_reclaimed_space(self):
        outcome = views.PromptViewTests().outcome('x'*900, argv=('cat', 'x'))
        sources, _ = observation_sources(outcome, 1700)
        self.assertEqual(sources[0]['stdout'], 'x'*900)
        self.assertFalse(sources[0]['display_truncated'])
        self.assertLessEqual(len(compact(sources)), 1700)

if __name__ == '__main__':
    unittest.main()
