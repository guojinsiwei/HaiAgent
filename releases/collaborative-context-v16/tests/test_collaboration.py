import copy
import os
import unittest
from unittest.mock import patch

from bestfgs.collaboration import CollaborativePolicyAdapter, role_config_from_environment, role_system
from bestfgs.agent import TaskRunner
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.models import TaskSpec, StructuredContext, ModelCallError
from examples.demo_counter import CounterEnvironment
from test_retrac_adapter import ScriptedClient, model_config

PLAN = {'semantic_directions': [{'direction_id': 'counter', 'label': 'Counter', 'status': 'unexplored', 'evidence': []}],
        'bootstrap_action': {'name': 'add', 'rationale': 'observe counter', 'semantic_direction_id': 'counter',
            'semantic_direction_label': 'Counter', 'intent': 'explore', 'expected_effect': 'counter increases',
            'commands': [{'argv': ['counter', 'add', '1'], 'description': 'increment'}], 'verification_commands': []}}
ASSESSMENT = {'assessment': {'direction_status': 'exploring', 'task_success': False,
                            'satisfied_success_criteria': [], 'feedback': 'Actual counter output was 1'}}
MEMORY = {'next_context': {'task_goal': 'Reach 3', 'current_solution': 'counter=1',
          'facts_and_evidence': [{'claim': 'counter=1', 'source': 'counter add 1', 'verified': 'yes'}],
          'analysis_and_conclusions': [], 'unresolved_issues': ['Reach 3'], 'incomplete_plans': [],
          'semantic_directions': [{'direction_id': 'counter', 'label': 'Counter', 'status': 'exploring', 'evidence': ['counter=1']}],
          'environment_summary': 'counter=1'}, 'micro_experiences': []}

class CollaborationTests(unittest.TestCase):
    def make(self, assessment=None, memory=None, mode='conditioned'):
        clients = {'action': ScriptedClient([copy.deepcopy(PLAN)]),
                   'assessment': ScriptedClient(copy.deepcopy(assessment if assessment is not None else [ASSESSMENT])),
                   'memory': ScriptedClient(copy.deepcopy(memory if memory is not None else [MEMORY]))}
        adapter = CollaborativePolicyAdapter(model_config(), clients=clients, experience_mode=mode)
        return adapter, clients

    def transition(self, adapter):
        task = TaskSpec('counter-task', 'Reach 3', success_criteria=('counter=3',))
        context = StructuredContext(task_goal=task.goal)
        plan = adapter.propose_initial_plan(task=task, context=context, rules=(), limit=1)
        env = CounterEnvironment()
        outcome = env.execute(env.initial_snapshot(), plan.bootstrap_action, 4)
        return adapter.update_transition(task=task, previous=context, action=plan.bootstrap_action, outcome=outcome)

    def test_real_transition_is_split_and_merged(self):
        adapter, clients = self.make()
        result = self.transition(adapter)
        self.assertEqual(result.next_context.current_solution, 'counter=1')
        self.assertFalse(result.assessment.task_success)
        self.assertEqual([len(c.prompts) for c in clients.values()], [1, 1, 1])
        self.assertNotIn('Return the assessment and next_context together', clients['memory'].prompts[0])
        self.assertIn('Actual result source list', clients['assessment'].prompts[0])
        self.assertNotIn('Actual counter output was 1', clients['memory'].prompts[0])
        self.assertEqual(clients['assessment'].prompt_cache_keys, ['bestfgs-v15-assessment'])

    def test_each_role_prompt_has_one_responsibility(self):
        for mode in ('conditioned', 'legacy', 'off'):
            for role in ('action', 'assessment', 'memory'):
                prompt = role_system(role, mode)
                self.assertNotIn('Your responsibilities are', prompt)
                self.assertIn('You only', prompt)

    def test_memory_cannot_override_assessment_and_retries_only_itself(self):
        bad = dict(MEMORY, assessment={'task_success': True})
        adapter, clients = self.make(memory=[bad, MEMORY])
        self.transition(adapter)
        self.assertEqual(len(clients['assessment'].prompts), 1)
        self.assertEqual(len(clients['memory'].prompts), 2)

    def test_assessor_cannot_emit_memory(self):
        bad = copy.deepcopy(ASSESSMENT)
        bad['assessment']['micro_experiences'] = []
        adapter, clients = self.make(assessment=[bad, ASSESSMENT])
        self.transition(adapter)
        self.assertEqual(len(clients['assessment'].prompts), 2)
        self.assertEqual(len(clients['memory'].prompts), 1)

    def test_unsupported_success_claim_is_rejected(self):
        bad = copy.deepcopy(ASSESSMENT)
        bad['assessment']['task_success'] = True
        adapter, clients = self.make(assessment=[bad, bad])
        with self.assertRaises(ModelCallError):
            self.transition(adapter)
        self.assertEqual(len(clients['memory'].prompts), 0)

    def test_memory_off_does_not_accept_experience(self):
        valid = {'next_context': MEMORY['next_context']}
        adapter, clients = self.make(memory=[MEMORY, valid], mode='off')
        result = self.transition(adapter)
        self.assertEqual(result.assessment.micro_experiences, ())
        self.assertEqual(len(clients['memory'].prompts), 2)

    def test_role_failure_propagates_no_fallback(self):
        adapter, clients = self.make(memory=[{'commands': []}, {'commands': []}])
        with self.assertRaises(ModelCallError):
            self.transition(adapter)
        self.assertEqual(len(clients['action'].prompts), 1)

    def test_graph_runtime_still_drives_tool_budget(self):
        adapter, clients = self.make()
        result = TaskRunner(CounterEnvironment(), adapter,
            BestFGSConfig(max_iterations=1, max_total_tool_calls=4, initial_branching_factor=1)).run(
                TaskSpec('counter-task', 'Reach 3', success_criteria=('counter=3',)))
        self.assertEqual(result.total_tool_calls, 1)
        self.assertEqual(len(result.transitions), 1)
        self.assertFalse(result.submitted)

    def test_usage_aggregates_all_roles_without_keys(self):
        adapter, clients = self.make()
        for client in clients.values():
            client.usage_summary = lambda: {'model_calls': 2, 'api_requests': 3, 'prompt_tokens': 10,
                'cached_prompt_tokens': 2, 'cache_miss_prompt_tokens': 8, 'completion_tokens': 5}
        summary = adapter.model_usage_summary()
        self.assertEqual(summary['model_calls'], 6)
        self.assertEqual(summary['api_requests'], 9)
        self.assertEqual(summary['prompt_tokens'], 30)
        self.assertEqual(summary['cache_hit_rate'], 0.2)
        self.assertNotIn('secret', str(summary))

    def test_distinct_clients_required(self):
        same = ScriptedClient([])
        with self.assertRaises(ValueError):
            CollaborativePolicyAdapter(model_config(), clients={r: same for r in ('action', 'assessment', 'memory')})

    def test_memory_keeps_original_evidence_index_gate(self):
        memory = copy.deepcopy(MEMORY)
        item = {'operation': 'counter_step', 'target_paths': [], 'premises': [],
                'source_channel': 'command', 'source_index': 0,
                'lesson': 'Observed counter increment; future applicability unverified', 'next_check': 'Read counter'}
        memory['micro_experiences'] = [item, dict(item, source_index=99)]
        adapter, _ = self.make(memory=[memory])
        result = self.transition(adapter)
        self.assertEqual(len(result.assessment.micro_experiences), 1)
        self.assertEqual(result.assessment.micro_experiences_dropped, 1)

    def test_last_role_error_is_preserved_for_existing_runner(self):
        adapter, clients = self.make(memory=[{'commands': []}, {'commands': []}])
        clients['memory'].last_failure_kind = None
        clients['memory'].usage_summary = lambda: {'last_failure_kind': clients['memory'].last_failure_kind}
        with self.assertRaises(ModelCallError):
            self.transition(adapter)
        summary = adapter.model_usage_summary()
        self.assertEqual(summary['last_role'], 'memory')
        self.assertEqual(summary['last_failure_kind'], 'model_output')

    def test_overrides_preserve_budgets(self):
        base = model_config()
        with patch.dict(os.environ, {'BESTFGS_MEMORY_MODEL': 'small-model'}, clear=True):
            config = role_config_from_environment(base, 'memory')
        self.assertEqual(config.model_name, 'small-model')
        self.assertEqual(config.max_commands_per_action, base.max_commands_per_action)
        self.assertEqual(config.parse_attempts, base.parse_attempts)

    def test_different_endpoint_cannot_receive_base_key(self):
        with patch.dict(os.environ, {'BESTFGS_MEMORY_BASE_URL': 'https://other.invalid/v1'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'API_KEY_ENV'):
                role_config_from_environment(model_config(), 'memory')

if __name__ == '__main__':
    unittest.main()
