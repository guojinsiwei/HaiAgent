"""Graph acceptance: actual sibling restoration, scripted models, no API."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.graph_runtime import GraphTaskRunner
from bestfgs.graph_search import GraphLimits, StateNode, frontier_priority, parse_proposals
from bestfgs.lean_audit import read_trace, digest
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import CommandSpec, CommandResult, TaskSpec
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


def batch(*actions):
    return dict(candidates=[dict(kind='probe', hypothesis='Inspect this concrete option',
        expected_evidence='Compare its actual output', action=a) for a in actions])


class BranchEnvironment(FakeEnvironment):
    def __init__(self):
        super().__init__()
        self.starts = []

    def execute(self, action, deadline):
        self.starts.append(self.value)
        if action['argv'][0]=='branch':
            self.executed.append(action)
            self.value=action['argv'][1]
            failed=self.value=='A'
            return CommandResult(CommandSpec(tuple(action['argv']),'fixture'),
                int(failed),self.value,'branch rejected' if failed else '',0)
        if action['argv'][0]=='pytest':
            self.executed.append(action)
            failed=self.value!='B'
            return CommandResult(CommandSpec(tuple(action['argv']),'fixture'),int(failed),
                '=== 1 failed in 0.1s ===' if failed else '=== 1 passed in 0.1s ===','',0)
        return super().execute(action, deadline)


class FileBranchEnvironment(BranchEnvironment):
    """Portable file snapshot fixture, not a production sandbox."""
    def __init__(self, root):
        super().__init__()
        self.root=Path(root)
        self.workspace=self.root/'live'
        self.workspace.mkdir()
        self.saved={}
        self.value='seed'

    @property
    def value(self):
        return (self.workspace/'config.txt').read_text()

    @value.setter
    def value(self, value):
        if hasattr(self,'workspace'):
            (self.workspace/'config.txt').write_text(value)

    def checkpoint(self, label):
        identifier='snap'+str(len(self.saved))
        path=self.root/identifier
        shutil.copytree(self.workspace,path)
        record=dict(id=identifier,path=str(path),fingerprint=self.scope(),label=label)
        self.saved[identifier]=record
        return dict(record)

    def restore(self, record):
        if self.saved.get(record['id'])!=record:
            raise ValueError('unowned fixture snapshot')
        # Retain displaced fixture data; never delete a seed or user directory.
        self.workspace.rename(self.root/('retired-'+str(len(list(self.root.glob('retired-*'))))))
        shutil.copytree(record['path'],self.workspace)


class GraphAgentTests(unittest.TestCase):
    def exercise(self, responses, *, env=None, limits=None, monitor=None, **options):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        config=dict(max_turns=30,max_tools=20,memory_reliability=True,
            outcome_reliability=True,memory_decision=False,memory_injection=False,
            diagnostic_advisor_threshold=100,repeated_failure_threshold=100)
        config.update(options)
        actor=Scripted(responses)
        environment=env or BranchEnvironment()
        runner=GraphTaskRunner(environment,actor,Scripted([dict(alternatives=[])]*10),
            LeanConfig(**config),Path(temp.name)/'audit',monitor_client=monitor,graph_limits=limits)
        result=runner.run(TaskSpec('fixture','Inspect config and deliver corrected files'))
        return result,runner,actor,read_trace(Path(temp.name)/'audit/events.jsonl')

    def test_failed_child_switches_to_sibling_from_exact_parent(self):
        env=BranchEnvironment()
        result,runner,actor,events=self.exercise(
            [batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],env=env)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(env.starts,['seed','seed'])
        self.assertEqual(result['artifact']['value'],'B')
        self.assertEqual(result['tool_calls'],2)
        self.assertEqual(result['interaction_rounds'],2)
        executed=[e for e in runner.search_edges.values() if e.status=='executed']
        self.assertEqual([e.source for e in executed],['N0','N0'])
        self.assertEqual(result['mechanism_utilization']['branch_restores'],1)
        self.assertTrue(any(e['event']=='graph_restore' and e['files_restored'] for e in events))
        evidence=actor.prompts[1]['fixed_context']['evidence']
        self.assertEqual([e['id'] for e in evidence],['E2'])
        self.assertNotIn('branch rejected',json.dumps(actor.prompts[1]))
        self.assertNotIn('branch rejected',json.dumps(runner.search_nodes['N0'].runtime['conversation'].turns))
        self.assertIsNone(result['official_success'])

    def test_actual_file_snapshots_preserve_both_paths(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env=FileBranchEnvironment(temp.name)
        result,runner,_,_=self.exercise(
            [batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],env=env)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(env.starts,['seed','seed'])
        self.assertEqual((env.workspace/'config.txt').read_text(),'B')
        values={(Path(n.record['path'])/'config.txt').read_text() for n in runner.search_nodes.values()}
        self.assertEqual(values,{'seed','A','B'})

    def test_reads_create_knowledge_nodes_and_cached_repeat_merges(self):
        read=run_action('read','config.txt')
        result,runner,_,events=self.exercise([batch(read),batch(read),SUBMIT])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['mechanism_utilization']['graph_cached_results'],1)
        self.assertEqual(result['mechanism_utilization']['graph_state_merges'],1)
        self.assertEqual(len(runner.search_nodes),2)
        self.assertEqual(result['mechanism_utilization']['graph_snapshots'],1)
        self.assertEqual(runner.search_nodes['N0'].observations,frozenset())
        self.assertTrue(runner.search_nodes['N1'].observations)
        self.assertTrue(any(e['event']=='graph_state_merge' for e in events))

    def test_duplicate_batch_does_not_execute_both_commands(self):
        read=run_action('read','config.txt')
        result,_,_,_=self.exercise([batch(read,read),SUBMIT])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['mechanism_utilization']['graph_duplicate_proposals'],1)

    def test_persistent_same_proposals_exhaust_frontier_with_bounded_calls(self):
        read=run_action('read','config.txt')
        result,_,_,_=self.exercise([batch(read)]*20)
        self.assertEqual(result['stop_reason'],'graph_frontier_exhausted')
        self.assertEqual(result['interaction_rounds'],4)
        self.assertEqual(result['tool_calls'],1)
        self.assertFalse(result['submitted'])

    def test_new_file_state_can_reexecute_same_check(self):
        check=run_action('pytest')
        # A failed state remains expandable after the root alternatives have
        # been consumed; it is not permanently excluded as an algorithm route.
        result,runner,_,_=self.exercise([batch(run_action('branch','B')),
            batch(check),batch(run_action('write','changed')),batch(check),SUBMIT],
            limits=GraphLimits(max_expansions_per_node=1))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(sum(a['argv'][0]=='pytest' for a in runner.environment.executed),2)
        self.assertEqual(result['mechanism_utilization'].get('graph_cached_results',0),0)

    def test_public_check_maturity_is_invalidated_by_file_change(self):
        result,runner,_,_=self.exercise([batch(run_action('branch','B')),batch(run_action('pytest')),
            batch(run_action('write','changed')),SUBMIT],limits=GraphLimits(max_expansions_per_node=1))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(runner.search_nodes['N2'].public_checks.popitem()[1],'public_check_passed')
        self.assertEqual(runner.search_nodes['N3'].public_checks,{})
        self.assertEqual(result['artifact']['value'],'changed')  # explicit submission is not overwritten

    def test_model_budget_is_global_and_queued_edges_do_not_hide_requests(self):
        result,runner,_,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B'))],max_turns=1)
        self.assertEqual(result['interaction_rounds'],1)
        self.assertEqual(result['tool_calls'],2)
        self.assertEqual(result['stop_reason'],'graph_frontier_exhausted')
        self.assertEqual(runner.counts['model_requests'],runner.counts['action_calls'])

    def test_monitor_and_advisor_use_current_branch_and_common_model_budget(self):
        review=dict(verdict='stalled',reason='Repeated config inspection',evidence_ids=['E1','E2'],
            next_check='Inspect config parsing code',memories=[])
        result,runner,actor,events=self.exercise([batch(run_action('read','a')),
            batch(run_action('read','b')),SUBMIT],limits=GraphLimits(max_expansions_per_node=1),
            monitor=Scripted([review]),semantic_monitor=True,monitor_reliability=True,
            monitor_cooldown_tools=2,max_monitor_calls=2,max_tools=4)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['monitor_rounds'],1)
        self.assertEqual(result['advisor_rounds'],1)
        self.assertEqual(result['interaction_rounds'],5)
        self.assertTrue(any(e['event']=='advisor_handover' for e in events))

    def test_actor_memory_is_generated_retrieved_and_reviewed(self):
        fail=run_action('fail')
        memory=dict(kind='blocker',conclusion='Config command failed with same error',
            condition='Config remains unchanged',targets=[],evidence_ids=['E1'])
        remember=dict(run_action('read','config'),memory=memory)
        reviewed=dict(memory_review=dict(ids=['M1'],decision='recheck',
            observed_result='Config command failed',applicability='Same config files',
            reason='Inspect a different config source'),strategy_adjustment='Use a distinct config read',
            **run_action('read','other-config'))
        submit=dict(reviewed,**SUBMIT)
        result,runner,actor,events=self.exercise([batch(fail),batch(remember),batch(reviewed),submit],
            limits=GraphLimits(max_expansions_per_node=1),memory_decision=True,memory_injection=True)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(len(runner.memory.items),1)
        self.assertEqual(actor.prompts[2]['fixed_context']['memories'][0]['id'],'M1')
        self.assertTrue(any(e['event']=='memory_decision_review' for e in events))
        self.assertEqual(list(actor.prompts[2])[-1],'fixed_context')

    def test_snapshot_integrity_failure_is_not_reported_as_search_success(self):
        class BadRestore(BranchEnvironment):
            def restore(self,record): self.value='corrupted'
        result,_,_,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),SUBMIT],env=BadRestore())
        self.assertEqual(result['stop_reason'],'infrastructure_error')
        self.assertFalse(result['submitted'])

    def test_node_limit_is_explicit_and_does_not_reset_tools(self):
        result,_,_,_=self.exercise([batch(run_action('read','a')),batch(run_action('read','b'))],
            limits=GraphLimits(max_nodes=2,max_expansions_per_node=1))
        self.assertEqual(result['stop_reason'],'graph_node_budget')
        self.assertEqual(result['tool_calls'],1)

    def test_command_success_or_model_claim_is_not_public_check_success(self):
        node=StateNode('N0','s',{},information_new=True,files_changed=True)
        rank=frontier_priority(node,kind='repair',waiting=0,used_ratio=0)
        self.assertEqual(rank['public_checks_passed'],0)
        self.assertEqual(rank['semantics'],'heuristic_priority_not_task_correctness')

    def test_model_cannot_restore_and_partial_batch_cannot_execute(self):
        with self.assertRaises(ValueError):
            parse_proposals(batch(dict(action='restore',checkpoint_id='C1',reason='switch')),2)
        broken=batch(run_action('write','unsafe'),dict(action='invalid'))
        result,runner,_,_=self.exercise([broken]*3)
        self.assertEqual(result['tool_calls'],0)
        self.assertEqual(runner.environment.value,'seed')
        self.assertEqual(result['stop_reason'],'graph_frontier_exhausted')
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],2)

    def test_graph_does_not_mix_orthogonal_or_hai_route_controller(self):
        with self.assertRaises(ValueError):
            GraphTaskRunner(FakeEnvironment(),Scripted([]),Scripted([]),
                LeanConfig(contrastive_mode='orthogonal',memory_reliability=True,outcome_reliability=True),'unused')

    def test_memory_survives_sibling_switch_but_changed_conditions_are_labelled(self):
        class InitiallyWorking(BranchEnvironment):
            def execute(self,action,deadline):
                outcome=super().execute(action,deadline)
                if action['argv']==['branch','A']:
                    return replace(outcome,return_code=0,stderr='')
                return outcome
            def dependency_state(self,paths):
                return {p:'file:'+self.value for p in paths}
        memory=dict(kind='finding',conclusion='Config in branch A was observed',
            condition='Config contains A',targets=['config.json'],evidence_ids=['E1'])
        later=dict(run_action('fail'),memory=memory)
        result,runner,actor,_=self.exercise(
            [batch(run_action('branch','A'),run_action('branch','B')),batch(later),SUBMIT],
            env=InitiallyWorking(),limits=GraphLimits(max_expansions_per_node=1))
        self.assertTrue(result['submitted'],result)
        shown=actor.prompts[-1]['fixed_context']['memories']
        self.assertEqual(shown[0]['id'],'M1')
        self.assertEqual(shown[0]['applicability'],'target_dependencies_changed_or_unknown_recheck_required')
        self.assertEqual(runner.memory.items['M1']['dependency_state'],{'config.json':'file:A'})
        self.assertEqual(result['artifact']['value'],'B')

    def test_external_retry_is_one_bounded_reexecution_not_a_whitelist(self):
        read=run_action('read','config')
        retry=dict(read,loop_retry=dict(reason='External state might change',expected_change='READY'))
        result,_,_,_=self.exercise([batch(read),batch(retry),batch(retry),SUBMIT])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],2)
        self.assertGreaterEqual(result['mechanism_utilization'].get('graph_duplicate_proposals',0)
            + result['mechanism_utilization'].get('graph_cached_results',0),1)

    def test_graph_memory_prefix_applies_to_nested_actions_without_conflicting_top_level_rule(self):
        result,runner,_,events=self.exercise([SUBMIT],memory_decision=True,memory_injection=True)
        self.assertTrue(result['submitted'],result)
        system=next(e for e in events if e['event']=='final_prompt')['messages'][0]['content']
        self.assertIn('FIRST THREE keys in EACH nested candidate action object',system)
        self.assertNotIn('FIRST THREE top-level keys in the SAME JSON response',system)
        self.assertEqual(runner.counts['tool_calls'],0)

    def test_graph_limits_and_actual_tool_limit_remain_distinct(self):
        result,_,_,_=self.exercise([batch(run_action('read','a')),batch(run_action('read','b'))],max_tools=1)
        self.assertEqual(result['stop_reason'],'tool_budget')
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['interaction_rounds'],1)

    def test_queued_action_that_never_saw_new_memory_is_replanned_not_a_protocol_error(self):
        class InitiallyWorking(BranchEnvironment):
            def execute(self,action,deadline):
                result=super().execute(action,deadline)
                return replace(result,return_code=0,stderr='') if action['argv']==['branch','A'] else result
        remember=dict(run_action('fail'),memory=dict(kind='finding',
            conclusion='Config in branch A was observed',condition='Config contains A',
            targets=[],evidence_ids=['E1']))
        def reviewed(action):
            return dict(memory_review=dict(ids=['M1'],decision='not_applicable',
                observed_result='A was observed',applicability='We restored the root config',
                reason='The old branch observation is historical'),
                strategy_adjustment='Try the alternative from its original parent',**action)
        result,_,_,_=self.exercise([batch(run_action('branch','A'),run_action('branch','B')),
            batch(remember),batch(reviewed(run_action('branch','B'))),reviewed(SUBMIT)],
            env=InitiallyWorking(),memory_injection=True,memory_decision=True)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['mechanism_utilization']['graph_stale_proposals'],1)
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],0)
        self.assertEqual(result['artifact']['value'],'B')


if __name__=='__main__':
    unittest.main()
