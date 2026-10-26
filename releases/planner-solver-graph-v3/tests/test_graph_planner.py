"""No API: global planning, local solving and authority/budget boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from test_graph_agent import BranchEnvironment, FileBranchEnvironment, batch
from test_lean import Scripted, run_action, SUBMIT
from bestfgs.graph_planner import PlannerSolverGraphRunner, PlannerLimits
from bestfgs.graph_search import GraphLimits
from bestfgs.lean_audit import read_trace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec, ModelCallError


def plan(kind='expand',identifier='N0',**extra):
    return dict(selection=dict(kind=kind,id=identifier),reason='Compare observed config evidence',
        subgoal='Inspect and repair the selected config',success_observation='An explicit config check passes',**extra)


class ChoosingPlanner:
    def __init__(self,responses=()):
        self.responses=list(responses)
        self.prompts=[]
    def complete_json(self,**kwargs):
        payload=json.loads(kwargs['user_prompt'])
        self.prompts.append(payload)
        if self.responses:
            value=self.responses.pop(0)
            if isinstance(value,Exception):
                raise value
            return value(payload) if callable(value) else value
        choice=payload['frontier'][0]
        return plan(choice['kind'],choice['id'])


class PlannerTests(unittest.TestCase):
    def exercise(self,actions,*,plans=(),planner_limits=None,limits=None,planner=None,env=None,goal=None,
                 monitor=None,advice=(),**options):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        config=dict(max_turns=30,max_tools=20,memory_reliability=True,outcome_reliability=True,
            memory_decision=False,memory_injection=False,
            repeated_failure_threshold=100,diagnostic_advisor_threshold=100)
        config.update(options)
        actor=Scripted(actions)
        planner=planner or ChoosingPlanner(plans)
        runner=PlannerSolverGraphRunner(env or BranchEnvironment(),actor,Scripted(advice),LeanConfig(**config),
            Path(temp.name)/'audit',planner_client=planner,planner_limits=planner_limits,
            graph_limits=limits or GraphLimits(max_expansions_per_node=1),monitor_client=monitor)
        result=runner.run(TaskSpec('planner-fixture',goal or 'Inspect config and deliver corrected files'))
        events=read_trace(Path(temp.name)/'audit/events.jsonl')
        return result,runner,actor,planner,events

    def test_planner_supplies_local_goal_before_solver_writes_commands(self):
        initial=plan();initial['subgoal']='Inspect config headers before editing'
        result,runner,actor,planner,events=self.exercise([batch(run_action('read','config')),SUBMIT],plans=[initial])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(actor.prompts[0]['solver_assignment']['subgoal'],initial['subgoal'])
        self.assertEqual(actor.prompts[0]['solver_assignment']['source_node'],'N0')
        self.assertEqual(result['planner_rounds'],1)
        self.assertEqual(result['interaction_rounds'],result['action_rounds']+result['planner_rounds'])
        self.assertEqual(runner.planner_links['G1']['proposed_under'],'P1')
        self.assertEqual(runner.planner_outcomes[0]['evidence_id'],'E1')
        self.assertIsNone(runner.planner_outcomes[0]['selected_by'])  # automatic unambiguous execution
        self.assertFalse(runner.planner_outcomes[0]['causal_benefit_proven'])

    def test_planner_can_choose_second_sibling_over_default_ranking(self):
        result,runner,_,planner,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            plans=[plan(),plan('edge','G2')])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.environment.executed[0]['argv'],['branch','B'])
        self.assertEqual(result['artifact']['value'],'B')
        self.assertEqual(planner.prompts[1]['trigger'],'new_fork')
        self.assertEqual(runner.planner_links['G2']['selected_by'],'P2')

    def test_backtrack_restores_parent_and_failed_node_gets_semantic_annotation(self):
        update=dict(node_id='N1',hypothesis='A breaks config',status='parked',
            reason='The observed command failed',evidence_ids=['E1'])
        result,runner,actor,planner,events=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            plans=[plan(),plan('edge','G1'),plan('edge','G2',node_updates=[update])])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.environment.starts,['seed','seed'])
        self.assertEqual(result['artifact']['value'],'B')
        self.assertEqual(runner.node_plans['N1']['status'],'parked')
        self.assertEqual(runner.node_plans['N1']['interpretation'],'planner_hypothesis_not_verified')
        self.assertEqual(planner.prompts[2]['trigger'],'new_failed_state')
        self.assertEqual(actor.prompts[-1]['solver_assignment']['id'],'P3')
        self.assertEqual(runner.search_nodes['N1'].runtime['solver_assignment']['id'],'P2')
        self.assertTrue(any(e['event']=='graph_restore' and e['files_restored'] for e in events))

    def test_unknown_selection_falls_back_without_solver_protocol_error(self):
        result,runner,_,_,events=self.exercise([SUBMIT],plans=[plan('edge','G999')])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['planner_deferred'],1)
        self.assertEqual(runner.counts['protocol_errors'],0)
        self.assertEqual(result['tool_calls'],0)
        self.assertTrue(any(e['event']=='planner_deferred' for e in events))

    def test_planner_cannot_inject_a_command_or_fabricate_graph_edges(self):
        bad=dict(plan(),command=run_action('write','unauthorized'))
        result,runner,_,_,_=self.exercise([SUBMIT],plans=[bad])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.environment.value,'seed')
        self.assertEqual(result['tool_calls'],0)
        self.assertEqual(len(runner.search_edges),1)
        self.assertEqual(runner.counts['planner_deferred'],1)

    def test_cross_branch_citation_is_rejected_without_discarding_valid_selection(self):
        bad=dict(node_id='N0',hypothesis='A failed',status='parked',
            reason='Wrong branch citation',evidence_ids=['E1'])
        result,runner,_,_,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            plans=[plan(),plan('edge','G1'),plan('edge','G2',node_updates=[bad])])
        self.assertTrue(result['submitted'],result)
        self.assertNotIn('N0',runner.node_plans)
        self.assertEqual(runner.counts['planner_annotations_rejected'],1)
        self.assertEqual(runner.counts['planner_decisions_accepted'],3)

    def test_parked_is_not_permanent_pruning(self):
        update=dict(node_id='N0',hypothesis='Need another approach',status='parked',
            reason='Tentative prioritization',evidence_ids=[])
        result,runner,_,_,_=self.exercise([batch(run_action('read','config')),SUBMIT],
            plans=[plan(node_updates=[update])])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(runner.search_edges['G1'].priority['planner_overlay_adjustment'],-.05)

    def test_one_global_request_left_is_reserved_for_solver(self):
        result,runner,_,planner,_=self.exercise([SUBMIT],max_turns=1)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['interaction_rounds'],1)
        self.assertEqual(result['planner_rounds'],0)
        self.assertEqual(planner.prompts,[])

    def test_planner_quota_exhaustion_keeps_bounded_solver_running(self):
        result,runner,_,planner,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            planner_limits=PlannerLimits(max_calls=1))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['planner_rounds'],1)
        self.assertEqual(runner.environment.starts,['seed','seed'])
        self.assertEqual(result['interaction_rounds'],3)

    def test_transient_planner_model_failure_is_optional_not_task_failure(self):
        result,runner,_,_,_=self.exercise([SUBMIT],plans=[ModelCallError('fixture')])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.counts['planner_deferred'],1)
        self.assertEqual(result['interaction_rounds'],2)

    def test_all_memory_remains_tail_positioned_for_solver_and_planner(self):
        result,_,actor,planner,_=self.exercise([SUBMIT],memory_injection=True,memory_decision=True)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(list(actor.prompts[0])[-1],'fixed_context')
        self.assertEqual(list(planner.prompts[0])[-1],'fixed_context')

    def test_unadvertised_choice_cannot_escape_compact_frontier(self):
        result,runner,_,planner,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            planner_limits=PlannerLimits(max_frontier_choices=1,max_calls=2),
            plans=[plan(),plan('edge','G2')])
        self.assertTrue(result['submitted'],result)
        self.assertGreater(planner.prompts[1]['omitted_frontier_count'],0)
        self.assertEqual(runner.counts['planner_deferred'],1)
        self.assertEqual(runner.environment.executed[0]['argv'],['branch','A'])

    def test_periodic_planning_not_required_for_every_read(self):
        actions=[batch(run_action('read',str(i))) for i in range(5)]+[SUBMIT]
        result,_,_,planner,_=self.exercise(actions,planner_limits=PlannerLimits(interval_steps=4))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['planner_rounds'],2)
        self.assertEqual([p['trigger'] for p in planner.prompts],['initial_subgoal','progress_checkpoint'])

    def test_distinct_client_instances_required(self):
        actor=Scripted([])
        with self.assertRaisesRegex(ValueError,'independent'):
            PlannerSolverGraphRunner(BranchEnvironment(),actor,Scripted([]),
                LeanConfig(memory_reliability=True,outcome_reliability=True),'unused',planner_client=actor)

    def test_planner_selected_restore_uses_actual_file_snapshot(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        env=FileBranchEnvironment(directory.name)
        result,runner,_,_,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],
            env=env,plans=[plan(),plan('edge','G1'),plan('edge','G2')])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(env.starts,['seed','seed'])
        self.assertEqual((env.workspace/'config.txt').read_text(),'B')
        values={(Path(n.record['path'])/'config.txt').read_text() for n in runner.search_nodes.values()}
        self.assertEqual(values,{'seed','A','B'})

    def test_planner_context_overflow_skips_request_without_truncating_task(self):
        goal='Inspect config. '+('bounded task description '*220)
        result,runner,actor,planner,events=self.exercise([SUBMIT],goal=goal,
            planner_limits=PlannerLimits(context_chars=8000))
        self.assertTrue(result['submitted'],result)
        self.assertFalse(planner.prompts)
        self.assertEqual(result['planner_rounds'],0)
        self.assertEqual(actor.prompts[0]['task']['goal'],goal)
        self.assertEqual(runner.counts['planner_deferred'],1)

    def test_planner_retains_last_solver_request_under_tight_global_budget(self):
        result,runner,actor,planner,_=self.exercise([SUBMIT],max_turns=2)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['interaction_rounds'],2)
        self.assertEqual(result['planner_rounds'],1)
        self.assertEqual(result['action_rounds'],1)

    def test_task_memory_reaches_both_roles_without_invalidating_fresh_solver_proposals(self):
        remember=dict(run_action('read','config'),memory=dict(kind='finding',
            conclusion='Config read returned seed',condition='Config unchanged',targets=[],evidence_ids=['E1']))
        def reviewed(action):
            return dict(memory_review=dict(ids=['M1'],decision='recheck',observed_result='Config returned seed',
                applicability='Same config',reason='Check a distinct source'),
                strategy_adjustment='Inspect another config source',**action)
        result,runner,actor,planner,_=self.exercise([batch(run_action('read','initial')),batch(remember),
            batch(reviewed(run_action('read','other'))),reviewed(SUBMIT)],
            memory_injection=True,memory_decision=True,planner_limits=PlannerLimits(interval_steps=2))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(planner.prompts[-1]['fixed_context']['memories'][0]['id'],'M1')
        self.assertEqual(actor.prompts[2]['fixed_context']['memories'][0]['id'],'M1')
        self.assertEqual(runner.counts['graph_stale_proposals'],0)
        self.assertEqual(runner.counts['protocol_errors'],0)

    def test_four_roles_link_advice_planning_and_actual_execution_under_one_budget(self):
        from test_graph_collaboration import REVIEW, ALTERNATIVE, PROBE
        action=dict(PROBE,advice_review=dict(advice_id='A1',alternative_id='H1',
            decision='adopt',reason='Check the suggested evidence'))
        result,runner,actor,planner,events=self.exercise([batch(run_action('read','a')),
            batch(run_action('read','b')),batch(action),SUBMIT],
            monitor=Scripted([REVIEW]),advice=[dict(alternatives=[ALTERNATIVE])],
            semantic_monitor=True,monitor_reliability=True,monitor_cooldown_tools=2,max_monitor_calls=6,max_tools=10)
        self.assertTrue(result['submitted'],result)
        self.assertEqual((result['action_rounds'],result['planner_rounds'],result['monitor_rounds'],result['advisor_rounds']),
            (4,2,1,1))
        self.assertEqual(result['interaction_rounds'],8)
        self.assertEqual(planner.prompts[-1]['trigger'],'new_advice')
        self.assertEqual(actor.prompts[2]['solver_assignment']['id'],'P2')
        self.assertEqual(runner.cooperation_outcomes[0]['prediction_status'],'supported_observation')
        self.assertEqual(runner.planner_links['G3']['proposed_under'],'P2')


if __name__=='__main__':
    unittest.main()
