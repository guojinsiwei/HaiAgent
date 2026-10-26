from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from bestfgs.best_first_runtime import CandidateRegistry
from bestfgs.models import CommandSpec, CommandResult, ModelCallError, TransitionAssessment, TransitionUpdate
from bestfgs.validation import validation_passed
from test_delivery_runtime import DeliveryRuntimeTests, action, edit, python_command, public_test, read_source
from test_collaboration import CollaborationTests, MEMORY


class PublicValidationTests(unittest.TestCase):
    def result(self, text, **kw):
        return CommandResult(CommandSpec(('simulate','run'), 'public assertion'), 0, text, '', 0, **kw)

    def test_exit_zero_does_not_hide_explicit_failure(self):
        for text in ['Deadline met: 0/100 (0.0%)\nNormalized: 0.0000',
                     '=== 2 failed, 4 passed ===', 'FAILED (failures=1)', 'Overall score: 0.0']:
            self.assertFalse(validation_passed(self.result(text)))

    def test_incomplete_verification_is_not_passed(self):
        self.assertFalse(validation_passed(self.result('OK', output_truncated=True)))
        self.assertTrue(validation_passed(self.result('Ran 2 tests\nOK')))

    def test_candidate_selection_uses_comparable_fresh_scores_not_recency(self):
        registry=CandidateRegistry();graph=SimpleNamespace(nodes={})
        for name,score in [('good',.8),('worse',.2),('best',.9),('tie',.9)]:
            graph.nodes[name]=SimpleNamespace(node_id=name)
            registry.register_working(name,patch_sha256=name)
            result=self.result(f'Normalized: {score}')
            registry.register_verified(name,(result.command,),results=(result,))
        self.assertEqual(registry.best_verified(graph).node_id,'best')
        registry.register_working('best',patch_sha256='changed')
        self.assertFalse(registry.records['best'].local_validation_passed)
        self.assertFalse(registry.records['best'].public_measurements)


class RuntimeRegressionTests(DeliveryRuntimeTests):
    def test_zero_exit_broken_policy_does_not_replace_good_checkpoint(self):
        from pathlib import Path
        broken_report=python_command("print('Deadline met: 0/100 (0.0%)\\nNormalized: 0.0000')", 'simulate public behavior')
        checkpoint=self.root/'checkpoint.json'
        result=self.run_actions([
            action('good',[edit(1)],[public_test()]),
            action('broken',[edit(2)],[broken_report]),
        ],checkpoint=checkpoint)
        self.assertFalse(result.transitions[-1].outcome.functional_validation_succeeded)
        self.assertEqual((Path(result.best_node.snapshot.location)/'answer.py').read_text(),'VALUE = 1\n')
        data=json.loads(checkpoint.read_text(encoding='utf-8'))
        self.assertEqual(data['best_snapshot_fingerprint'],result.best_node.snapshot.fingerprint)
        self.assertNotEqual(data['delivery']['selection_reason'],'latest_publicly_validated_candidate')

    def test_assessment_failure_vetoes_false_positive_verifier(self):
        from unittest.mock import patch
        from test_delivery_runtime import ScriptedPolicy
        original=ScriptedPolicy.update_transition
        def assess(policy, **kw):
            update=original(policy, **kw)
            if kw['action'].name=='broken':
                update=replace(update,assessment=TransitionAssessment('failed',False,'semantic regression'))
            return update
        with patch.object(ScriptedPolicy,'update_transition',assess):
            result=self.run_actions([
                action('good',[edit(1)],[public_test()]),
                action('broken',[edit(2)],[python_command("print('report generated')",'report only')]),
            ])
        from pathlib import Path
        self.assertEqual((Path(result.best_node.snapshot.location)/'answer.py').read_text(),'VALUE = 1\n')


class MemoryDeltaTests(unittest.TestCase):
    def test_transport_error_is_not_hidden_as_optional_memory_loss(self):
        fixture=CollaborationTests();adapter,clients=fixture.make()
        def fail(**kwargs):
            raise ModelCallError('synthetic transport failure')
        clients['memory'].complete_json=fail
        with self.assertRaises(ModelCallError):
            fixture.transition(adapter)
        self.assertEqual(adapter.memory_updates_deferred,0)

    def test_memory_failure_preserves_valid_assessment(self):
        fixture=CollaborationTests();adapter,clients=fixture.make(memory=[{'commands':[]}])
        result=fixture.transition(adapter)
        self.assertIn('Actual counter',result.assessment.feedback)
        self.assertEqual(len(clients['memory'].prompts),1)
        self.assertEqual(adapter.model_usage_summary()['memory_updates_deferred'],1)

    def test_delta_prompt_and_transport_budget(self):
        fixture=CollaborationTests();adapter,clients=fixture.make(memory=[{'next_context':{}}])
        fixture.transition(adapter)
        self.assertIn('SPARSE delta',clients['memory'].prompts[0])
        self.assertNotIn('"task_goal": "original goal"',clients['memory'].prompts[0])
        self.assertLessEqual(adapter.role_configs['memory'].max_tokens,1536)
        self.assertEqual(adapter.role_configs['memory'].request_attempts,1)
        self.assertEqual(adapter.role_configs['memory'].parse_attempts,1)

    def test_identical_read_only_observation_skips_only_optional_memory(self):
        from examples.demo_counter import CounterEnvironment
        from bestfgs.models import TaskSpec,StructuredContext
        fixture=CollaborationTests();adapter,clients=fixture.make(assessment=[
            {'assessment':{'direction_status':'exploring','task_success':False,'satisfied_success_criteria':[], 'feedback':'actual output'}}]*4,
            memory=[{'next_context':{}}]*3)
        task=TaskSpec('T','read');previous=StructuredContext(task_goal='read')
        plan=adapter.propose_initial_plan(task=task,context=previous,rules=(),limit=1)
        env=CounterEnvironment();outcome=env.execute(env.initial_snapshot(),plan.bootstrap_action,4)
        outcome=replace(outcome,parent_snapshot=outcome.resulting_snapshot)
        for _ in range(3):
            adapter.update_transition(task=task,previous=previous,action=plan.bootstrap_action,outcome=outcome)
        self.assertEqual(len(clients['assessment'].prompts),3)
        self.assertEqual(len(clients['memory'].prompts),1)
        self.assertEqual(adapter.memory_updates_skipped,2)
        adapter.update_transition(task=task,previous=replace(previous,current_solution='different branch context'),
                                  action=plan.bootstrap_action,outcome=outcome)
        self.assertEqual(len(clients['memory'].prompts),2)
