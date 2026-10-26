import copy
import json
import unittest
from dataclasses import replace

from bestfgs.models import EvidenceItem, StructuredContext, SemanticDirection
from bestfgs.prompt_views import classify, compress_stream, observation_sources, context_and_memory, memory_panel, compact
from test_micro_experience_wire import adapter, action_payload, outcome_for
import test_collaboration as collaboration_tests

class PromptViewTests(unittest.TestCase):
    def outcome(self, text, argv=('pytest', '-q'), stderr=''):
        action, = adapter()._parse_actions({'actions': [action_payload()]}, limit=1)
        result = outcome_for(action)
        command = replace(result.command_results[0].command, argv=argv)
        actual = replace(result.command_results[0], command=command, stdout=text, stderr=stderr)
        return replace(result, command_results=(actual,), validation_results=(), functional_validation_results=())

    def test_simple_bash_can_be_classified(self):
        self.assertEqual(classify(('bash', '-lc', 'pytest -q')), 'test')
        self.assertEqual(classify(('bash', '-lc', 'rg "error|failure" src')), 'search')

    def test_shell_composition_remains_generic(self):
        for command in ('pytest -q | tail', 'cd /app && pytest', 'cat $(pwd)', 'cat `pwd`', 'ls; rm x', 'ls\npwd'):
            self.assertEqual(classify(('bash', '-lc', command)), 'generic')

    def test_common_commands(self):
        for argv, expected in ((('ls', '-la'), 'listing'), (('find', '.'), 'listing'),
            (('rg', 'x'), 'search'), (('git', 'diff'), 'diff'), (('cat', 'x'), 'read'),
            (('python3', '-m', 'pip', 'install', 'x'), 'install'), (('ninja',), 'build')):
            self.assertEqual(classify(argv), expected)

    def test_small_output_unchanged(self):
        raw = 'a\n\x1b[31mwarning\x1b[0m\n'
        self.assertEqual(compress_stream(raw, 'build', 1000), raw)

    def test_build_retains_middle_error_and_tail(self):
        raw = 'progress\n' * 500 + 'compiler error: missing header\n' + 'progress\n' * 500 + 'build failed\n'
        view = compress_stream(raw, 'build', 900)
        self.assertIn('compiler error: missing header', view)
        self.assertIn('build failed', view)
        self.assertIn('[L501]', view)
        self.assertLessEqual(len(view), 900)

    def test_test_output_preserves_failure_even_with_passing_tail(self):
        raw = 'running\n'*200 + 'FAILED test_counter.py::test_bad\n' + 'running\n'*200 + '1 failed, 30 passed in 2.0s\n'
        view = compress_stream(raw, 'test', 800)
        self.assertIn('FAILED test_counter', view)
        self.assertIn('1 failed, 30 passed', view)

    def test_source_and_diff_not_rewritten_into_summary(self):
        raw = 'def start():\n' + '    print(1)\n'*400 + 'raise ValueError("end")\n'
        view = compress_stream(raw, 'read', 500)
        self.assertIn('def start', view)
        self.assertIn('ValueError', view)
        self.assertIn('omitted', view)
        diff = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n' + '-old\n+new\n'*200
        view = compress_stream(diff, 'diff', 500)
        self.assertIn('diff --git', view)
        self.assertIn('@@', view)

    def test_observation_does_not_mutate_raw_result(self):
        outcome = self.outcome('line\n'*3000, stderr='AssertionError: x\n')
        before = copy.deepcopy(outcome)
        sources, counts = observation_sources(outcome, 2000)
        self.assertEqual(outcome, before)
        self.assertTrue(sources[0]['display_truncated'])
        self.assertFalse(sources[0]['output_truncated'])
        self.assertEqual(counts['command'], 1)
        self.assertEqual(sources[0]['source_index'], 0)
        self.assertIn('captured_stdout_sha256', sources[0])

    def test_json_escaping_budget(self):
        sources, _ = observation_sources(self.outcome('"\\\n控制\t'*3000), 1800)
        self.assertLessEqual(len(compact(sources)), 1800)

    def test_timeout_never_turns_into_success(self):
        outcome = self.outcome('100 passed in 1.0s')
        outcome = replace(outcome, command_results=(replace(outcome.command_results[0], timed_out=True, return_code=-9),))
        sources, _ = observation_sources(outcome, 2000)
        self.assertTrue(sources[0]['timed_out'])
        self.assertEqual(sources[0]['return_code'], -9)
        self.assertNotIn('success', sources[0])

    def test_tiny_observation_budget_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'source identities'):
            observation_sources(self.outcome('hello'), 10)

    def test_memory_has_reserved_space_and_complete_conditions(self):
        context = StructuredContext(task_goal='repair', analysis_and_conclusions=('long'*10000,))
        rule = {'rule_id': 'r1', 'condition': 'file contains old guard', 'guidance': 'recheck boundary',
                'evidence_ids': ['E3'], 'condition_status': 'unknown'}
        ordinary, memory = context_and_memory(context, [rule], mode='conditioned', max_chars=14000)
        self.assertLessEqual(len(ordinary), 11500)
        self.assertLessEqual(len(memory), 2500)
        self.assertEqual(json.loads(memory)['rules'][0], rule)

    def test_oversized_memory_omits_whole_record(self):
        context = StructuredContext(task_goal='repair')
        memory = json.loads(memory_panel(context, [{'guidance': 'x'*5000, 'condition': 'never omit me'}], mode='conditioned'))
        self.assertEqual(memory['rules'], [])
        self.assertEqual(memory['omitted_rules'], 1)

    def test_memory_does_not_claim_past_fact_still_current(self):
        context = StructuredContext(task_goal='repair', facts_and_evidence=(EvidenceItem('test passed', 'snapshot old', 'yes',
            workspace_dependencies=('src/x.py',), observed_at_fingerprint='old-snapshot'),))
        memory = json.loads(memory_panel(context, [], mode='conditioned'))
        fact = memory['observed_facts'][0]
        self.assertEqual(fact['source'], 'snapshot old')
        self.assertEqual(fact['verified_at_observation'], 'yes')
        self.assertEqual(fact['workspace_dependencies'], ['src/x.py'])
        self.assertEqual(fact['observed_at_fingerprint'], 'old-snapshot')
        self.assertIn('not current validity', memory['caution'])

    def test_off_mode_has_no_extra_memory(self):
        context = StructuredContext(task_goal='repair', facts_and_evidence=(EvidenceItem('fact', 'source', 'yes'),))
        memory = json.loads(memory_panel(context, [{'rule_id':'r'}], mode='off'))
        self.assertEqual(memory['rules'], [])
        self.assertEqual(memory['observed_facts'], [])

    def test_extreme_context_is_bounded_without_mutating_graph(self):
        directions = tuple(SemanticDirection(str(i), 'direction'*50, 'unexplored') for i in range(300))
        context = StructuredContext(task_goal='repair', semantic_directions=directions)
        ordinary, _ = context_and_memory(context, [], mode='conditioned', max_chars=4000)
        self.assertLessEqual(len(ordinary), 1500)
        self.assertGreater(json.loads(ordinary)['display_records_omitted'], 0)
        self.assertEqual(context.semantic_directions, directions)

    def test_all_three_roles_receive_memory_panel_without_extra_call(self):
        fixture = collaboration_tests.CollaborationTests()
        policy, clients = fixture.make()
        fixture.transition(policy)
        for client in clients.values():
            self.assertEqual(len(client.prompts), 1)
            self.assertIn('[TASK_MEMORY_BEGIN]', client.prompts[0])
        self.assertIn('terminal-views-v2/', clients['assessment'].prompts[0])

    def test_panel_rebuilt_from_current_branch_not_hidden_history(self):
        fixture = collaboration_tests.CollaborationTests()
        policy, _ = fixture.make()
        old = StructuredContext(task_goal='taskA', facts_and_evidence=(EvidenceItem('BRANCH_A_ONLY', 'snapshot A', 'yes'),))
        other = StructuredContext(task_goal='taskB')
        self.assertIn('BRANCH_A_ONLY', policy._prompt_context(old)[1])
        self.assertNotIn('BRANCH_A_ONLY', policy._prompt_context(other)[1])

    def test_disabled_views_keep_v15_prompt_path(self):
        fixture = collaboration_tests.CollaborationTests()
        policy, clients = fixture.make()
        policy.terminal_views = False
        fixture.transition(policy)
        for client in clients.values():
            self.assertNotIn('[TASK_MEMORY_BEGIN]', client.prompts[0])

    def test_view_audit_bounded_and_does_not_cache_prompt_memory(self):
        fixture = collaboration_tests.CollaborationTests()
        policy, _ = fixture.make()
        context = StructuredContext(task_goal='only task-local context')
        for _ in range(40):
            policy._prompt_context(context)
        report = policy.model_usage_summary()['prompt_views']
        self.assertEqual(report['built_count'], 40)
        self.assertEqual(len(report['retained_last']), 32)
        self.assertNotIn('only task-local context', str(report))
        self.assertEqual(report['retained_last'][-1]['visible_rule_ids'], [])

if __name__ == '__main__':
    unittest.main()
