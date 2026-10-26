"""Offline role cooperation contracts; scripted clients never use model APIs."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_graph_agent import BranchEnvironment, batch
from test_lean import Scripted, run_action, SUBMIT
from bestfgs.graph_collaboration import CollaborativeGraphRunner, parse_alternative
from bestfgs.graph_roles import collaborator_config
from bestfgs.graph_search import GraphLimits, StateNode, executable_key
from bestfgs.lean_audit import read_trace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig


PROBE=run_action('read','probe')
ALTERNATIVE=dict(id='H1',hypothesis='Config source may differ',check='Inspect the source',
    difference='Inspect source instead of repeating a test',evidence_ids=['E2'],
    probe=PROBE,prediction=dict(supports='seed',refutes='ERROR'))
REVIEW=dict(verdict='stalled',reason='Repeated config inspection',evidence_ids=['E1','E2'],
    next_check='Inspect config source',memories=[])


class CollaborationTests(unittest.TestCase):
    def exercise(self,responses,*,advisor=(),monitor=None,limits=None,runner_type=CollaborativeGraphRunner,**options):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        config=dict(max_turns=30,max_tools=20,memory_reliability=True,
            outcome_reliability=True,memory_decision=False,memory_injection=False,
            diagnostic_advisor_threshold=100,repeated_failure_threshold=100)
        config.update(options)
        actor=Scripted(responses)
        runner=runner_type(BranchEnvironment(),actor,Scripted(advisor),LeanConfig(**config),
            Path(temp.name)/'audit',monitor_client=monitor,graph_limits=limits)
        result=runner.run(TaskSpec('cooperation-fixture','Inspect config and deliver corrected files'))
        events=read_trace(Path(temp.name)/'audit/events.jsonl')
        return result,runner,actor,events

    def full_flow(self,*,decision='adopt',changed=False):
        action=dict(run_action('read','changed') if changed else PROBE,
            advice_review=dict(advice_id='A1',alternative_id='H1',decision=decision,
                reason='Use the suggested discriminating evidence'))
        candidates=batch(action) if changed or decision=='decline' else batch(run_action('read','unrelated'),action)
        return self.exercise([batch(run_action('read','a')),batch(run_action('read','b')),
            candidates,SUBMIT],
            advisor=[dict(alternatives=[ALTERNATIVE])],monitor=Scripted([REVIEW]),
            limits=GraphLimits(max_expansions_per_node=1),semantic_monitor=True,
            monitor_reliability=True,monitor_cooldown_tools=2,max_monitor_calls=6,max_tools=10)

    def test_full_monitor_advisor_actor_execution_outcome_link(self):
        result,runner,actor,events=self.full_flow()
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['interaction_rounds'],6)
        self.assertEqual(result['tool_calls'],3)
        self.assertEqual((result['monitor_rounds'],result['advisor_rounds']),(1,1))
        self.assertEqual([a['argv'][1] for a in runner.environment.executed],['a','b','probe'])
        self.assertEqual(runner.search_edges['G3'].status,'pending')  # unchosen sibling survives
        self.assertEqual(runner.guides['A1']['monitor_review_id'],'R1')
        self.assertEqual(runner.guides['A1']['source_node'],'N2')
        outcome=runner.cooperation_outcomes[0]
        self.assertTrue(outcome['actor_saw_advice'])
        self.assertTrue(outcome['new_evidence'])
        self.assertEqual(outcome['prediction_status'],'supported_observation')
        self.assertFalse(outcome['public_check_improved'])
        self.assertFalse(outcome['causal_benefit_proven'])
        self.assertIsNone(outcome['official_success'])
        self.assertEqual(len(runner.memory.items),0)  # unexecuted suggestions are not lessons
        self.assertTrue(any(e['event']=='cooperation_outcome' for e in events))
        self.assertIn('graph_collaboration',actor.prompts[2])

    def test_review_observes_failed_child_before_sibling_restore(self):
        monitor=Scripted([dict(verdict='uncertain',reason='Need another observation',
            evidence_ids=['E1'],next_check='Inspect config',memories=[])])
        result,runner,_,events=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            monitor=monitor,semantic_monitor=True,monitor_reliability=True,
            max_monitor_calls=4,monitor_cooldown_tools=1,max_tools=3)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(monitor.prompts[0]['current_workspace'],runner.search_nodes['N1'].scope)
        self.assertEqual(runner.monitor_registry['R1']['source_node'],'N1')
        linked=next(i for i,e in enumerate(events) if e['event']=='cooperation_monitor_link')
        restored=next(i for i,e in enumerate(events) if e['event']=='graph_restore' and e['files_restored'])
        self.assertLess(linked,restored)
        self.assertEqual(result['advisor_rounds'],0)

    def test_one_bad_alternative_preserves_valid_sibling(self):
        valid=dict(ALTERNATIVE,evidence_ids=[])
        invalid=dict(ALTERNATIVE,id='H2',evidence_ids=['E999'])
        result,runner,_,_=self.exercise([dict(action='consult',question='Inspect config?'),SUBMIT],
            advisor=[dict(alternatives=[valid,invalid])])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(len(runner.guides['A1']['alternatives']),1)
        self.assertEqual(runner.counts['advisor_alternatives_rejected'],1)
        self.assertEqual(runner.counts['protocol_errors'],0)

    def test_advisor_quota_cannot_be_bypassed_by_actor_requests(self):
        result,runner,_,_=self.exercise([dict(action='consult',question='First check?'),
            dict(action='consult',question='Second check?'),SUBMIT],
            advisor=[dict(alternatives=[])],max_advisor_calls=1,
            limits=GraphLimits(max_expansions_per_node=3))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['advisor_rounds'],1)
        self.assertEqual(result['interaction_rounds'],4)
        self.assertEqual(result['tool_calls'],0)

    def test_claimed_adoption_does_not_turn_changed_action_into_validated_prediction(self):
        result,runner,_,_=self.full_flow(changed=True)
        self.assertTrue(result['submitted'],result)
        outcome=runner.cooperation_outcomes[0]
        self.assertEqual(outcome['execution_alignment'],'changed_action')
        self.assertEqual(outcome['prediction_status'],'not_comparable_action_changed')
        self.assertEqual(runner.counts['advice_informative_predictions'],0)
        edge=runner.search_edges[outcome['edge_id']]
        self.assertIsNone(edge.priority['advisor_id'])

    def test_actor_can_decline_without_fatal_protocol_gate(self):
        result,runner,_,_=self.full_flow(decision='decline')
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['protocol_errors'],0)
        edge=runner.search_edges[runner.cooperation_outcomes[0]['edge_id']]
        self.assertIsNone(edge.priority['advisor_id'])

    def test_same_command_on_other_branch_does_not_inherit_advice(self):
        _,runner,_,_=self.full_flow()
        edge=deepcopy(runner.search_edges[runner.cooperation_outcomes[0]['edge_id']])
        edge.source='N0'
        self.assertEqual(runner._alignment(edge),{})

    def test_optional_prediction_requires_concrete_distinguishable_probe(self):
        with self.assertRaises(ValueError):
            parse_alternative(dict(ALTERNATIVE,prediction=dict(supports='error',refutes='no error')),{'E2'},1)
        with self.assertRaises(ValueError):
            parse_alternative(dict(ALTERNATIVE,probe=SUBMIT),{'E2'},1)
        text_only={k:v for k,v in ALTERNATIVE.items() if k not in {'probe','prediction'}}
        self.assertNotIn('probe',parse_alternative(text_only,{'E2'},1))

    def test_invalid_acknowledgement_is_logged_but_not_a_protocol_error(self):
        action=dict(PROBE,advice_review=dict(advice_id='A999',alternative_id='invented'))
        result,runner,_,_=self.exercise([dict(action='consult',question='Inspect config?'),batch(action),SUBMIT],
            advisor=[dict(alternatives=[dict(ALTERNATIVE,evidence_ids=[])])])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['advice_reviews_unlinked'],1)
        self.assertEqual(runner.counts['protocol_errors'],0)
        self.assertFalse(runner.cooperation_outcomes[0]['actor_decision']=='adopt')

    def test_unknown_check_suites_cannot_win_delivery_by_pass_count(self):
        _,runner,_,_=self.exercise([SUBMIT])
        active=runner.search_nodes['N0']
        active.public_checks={'suite-a':'public_check_failed'}
        unrelated=StateNode('NX','other',{},public_checks={'suite-b':'public_check_passed','suite-c':'public_check_passed'})
        runner.search_nodes['NX']=unrelated
        self.assertIs(runner._delivery_candidate(),active)
        comparable=StateNode('NY','other2',{},public_checks={'suite-a':'public_check_passed'})
        runner.search_nodes['NY']=comparable
        self.assertIs(runner._delivery_candidate(),comparable)

    def test_same_memory_id_with_changed_content_expires_queued_proposal(self):
        class UpdatedMemoryRunner(CollaborativeGraphRunner):
            changed=False
            def _expand(self,node):
                super()._expand(node)
                if self.visible_memories and not self.changed:
                    self.memory.items['M1']['condition']='Updated config condition needs a new review'
                    self.changed=True
        remember=dict(run_action('read','config'),memory=dict(kind='finding',
            conclusion='Config inspection returned seed',condition='Config remains unchanged',
            targets=[],evidence_ids=['E1']))
        def reviewed(action):
            return dict(memory_review=dict(ids=['M1'],decision='recheck',observed_result='Config failed',
                applicability='Inspect the current config',reason='A different config source is available'),
                strategy_adjustment='Inspect a distinct source',**action)
        result,runner,_,_=self.exercise([batch(run_action('read','initial')),batch(remember),
            batch(reviewed(run_action('read','other'))),batch(reviewed(run_action('read','other'))),reviewed(SUBMIT)],
            runner_type=UpdatedMemoryRunner,memory_decision=True,memory_injection=True)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['graph_stale_proposals'],1)
        self.assertEqual(runner.counts['protocol_errors'],0)

    def test_final_actor_memory_zone_is_still_last(self):
        result,_,actor,_=self.exercise([SUBMIT],memory_decision=True,memory_injection=True)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(list(actor.prompts[0])[-1],'fixed_context')

    def test_cached_probe_cannot_be_counted_as_a_fresh_prediction_test(self):
        result,runner,_,_=self.exercise([batch(PROBE),dict(action='consult',question='How to inspect config?'),
            batch(PROBE),SUBMIT],advisor=[dict(alternatives=[dict(ALTERNATIVE,evidence_ids=['E1'])])],
            limits=GraphLimits(max_expansions_per_node=3))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],1)
        outcome=runner.cooperation_outcomes[0]
        self.assertFalse(outcome['actual_execution'])
        self.assertFalse(outcome['new_evidence'])
        self.assertEqual(outcome['prediction_status'],'not_executed_cached_observation')
        self.assertEqual(runner.counts['advice_informative_predictions'],0)

    def test_all_roles_obey_one_global_request_limit(self):
        result,runner,_,_=self.exercise([batch(run_action('read','a')),batch(run_action('read','b'))],
            advisor=[dict(alternatives=[ALTERNATIVE])],monitor=Scripted([REVIEW]),
            limits=GraphLimits(max_expansions_per_node=1),semantic_monitor=True,
            monitor_reliability=True,monitor_cooldown_tools=2,max_monitor_calls=6,max_tools=10,max_turns=4)
        self.assertEqual(result['interaction_rounds'],4)
        self.assertEqual((result['action_rounds'],result['monitor_rounds'],result['advisor_rounds']),(2,1,1))
        self.assertEqual(result['tool_calls'],2)
        self.assertFalse(result['submitted'])
        self.assertEqual(len(runner.search_edges),2)  # advisor cannot inject an unapproved edge

    def test_advisor_bad_output_defers_without_stopping_actor(self):
        result,runner,_,_=self.exercise([dict(action='consult',question='Inspect config?'),SUBMIT],
            advisor=[dict(alternatives='bad output')])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['advisor_deferred'],1)
        self.assertEqual(runner.counts['protocol_errors'],0)
        self.assertFalse(runner.guides)

    def test_control_action_keys_preserve_history_pagination_and_submission(self):
        first=dict(action='recall_history',turn_ids=[1],offset=0)
        second=dict(first,offset=3000)
        self.assertNotEqual(executable_key(first),executable_key(second))
        self.assertNotEqual(executable_key(SUBMIT),executable_key(dict(action='consult',question='What changed?')))
        self.assertEqual(executable_key(SUBMIT),executable_key(dict(SUBMIT,summary='Different words')))

    def test_runner_reuse_is_rejected_without_erasing_previous_audit(self):
        _,runner,_,_=self.full_flow()
        old_guides=deepcopy(runner.guides)
        with self.assertRaisesRegex(RuntimeError,'single-use'):
            runner.run(TaskSpec('second-task','Inspect another config'))
        self.assertEqual(runner.guides,old_guides)

    def test_role_models_are_separate_configs_with_no_silent_endpoint_key_reuse(self):
        base=RetracModelConfig(model_name='actor-fixture',base_url='https://fixture.invalid/v1',api_key='test-only')
        observer=collaborator_config(base,'monitor',model_name='small-fixture')
        self.assertEqual(observer.model_name,'small-fixture')
        self.assertEqual(base.model_name,'actor-fixture')
        self.assertEqual(observer.request_attempts,1)
        self.assertFalse(observer.thinking_enabled)
        with self.assertRaises(ValueError):
            collaborator_config(base,'advisor',base_url='https://other.invalid/v1')
        with patch.object(RetracModelConfig,'from_environment',return_value=replace(base,api_key='other-test-only')) as read:
            collaborator_config(base,'advisor',model_name='advice-fixture',
                base_url='https://other.invalid/v1',api_key_env='TEST_ROLE_KEY')
            self.assertEqual(read.call_args.kwargs['api_key_env'],'TEST_ROLE_KEY')


if __name__=='__main__':
    unittest.main()
