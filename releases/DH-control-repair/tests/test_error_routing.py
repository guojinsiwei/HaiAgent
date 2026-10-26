"""Routes exercised at the real runner boundary, no provider calls."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.error_routing import RoutedTaskRunner,RoutingPolicy,readonly_action,execution_defect
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec,CommandSpec,CommandResult
from test_lean import FakeEnvironment,Scripted,run_action,SUBMIT

class StateEnvironment(FakeEnvironment):
    def __init__(self):
        super().__init__();self.dependencies={'f.py':'file:seed'};self.state={}
    def execute(self,action,deadline):
        self.executed.append(action);args=action['argv'];err='';code=0
        if args[0]=='edit':self.value=args[1];self.dependencies['f.py']='file:'+self.value
        if args[0]=='check' and self.value.startswith('bad'):code=1;err='assertion failed'
        if args[0]=='syntax':code=1;err='SyntaxError: invalid syntax'
        return CommandResult(CommandSpec(tuple(args),'fixture'),code,self.value,err,0)
    def checkpoint(self,label):
        record=super().checkpoint(label);self.state[record['id']]=dict(self.dependencies);return record
    def restore(self,record):
        super().restore(record);self.dependencies=dict(self.state[record['id']])

def goal():
    return {'id':'G1','title':'Public requirement','acceptance':'Output satisfies assertion',
            'depends_on':[],'targets':['f.py'],'verification':{'argv':['check'],'stdout_contains':['seed']}}

def critic(decision='accept',gaps=None,argv=None):
    return {'decision':decision,'requirements':['public requirement'],
            'gaps':gaps or [],'checks':[{'argv':argv or ['check'],'stdout_contains':['seed']}]}

class RouteTests(unittest.TestCase):
    def exercise(self,actions,policy=None,critics=(),env=None,config=None):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        actor=Scripted(actions);advisor=Scripted([])
        replies=[]
        for proposal in critics:
            replies.extend([proposal,dict(proposal,checks=[])])
        reviewer=Scripted(replies)
        config=config or LeanConfig(max_turns=40,max_tools=30,subgoals_enabled=True,
            contrastive_mode='orthogonal',contrastive_predictions=False,memory_reliability=True,
            outcome_reliability=True,memory_decision=False)
        runner=RoutedTaskRunner(env or StateEnvironment(),actor,advisor,config,Path(t.name)/'audit',
            routing=policy or RoutingPolicy(),critic_client=reviewer)
        result=runner.run(TaskSpec('fixture','Implement the public requirement'))
        return result,runner,read_trace(Path(t.name)/'audit/events.jsonl'),actor,reviewer

    def test_reconnaissance_classifier_rejects_side_effects(self):
        for argv in [['cat','f.py'],['bash','-c','head -n 10 f.py'],['rg','TODO','.']]:
            self.assertTrue(readonly_action(run_action(*argv)))
        for argv in [['bash','-c','cat f.py; rm f.py'],['bash','-c','cat $(touch x)'],
                     ['./cat','f.py'],['rg','--pre=touch x','TODO','.'],['git','diff','--output=x'],['python','-c','print(1)']]:
            self.assertFalse(readonly_action(run_action(*argv)))

    def test_defect_classifier_does_not_call_dependency_or_test_failure_syntax(self):
        self.assertEqual(execution_defect({'return_code':1,'stderr':'SyntaxError: bad'}),'syntax')
        self.assertIsNone(execution_defect({'return_code':1,'stderr':'ModuleNotFoundError: foo'}))
        self.assertIsNone(execution_defect({'return_code':0,'stdout':'SyntaxError: quoted'}))

    def test_three_arm_switches(self):
        for policy in [RoutingPolicy(),RoutingPolicy(critic=True),RoutingPolicy(critic=True,backtracking=True)]:
            r,engine,_,_,_=self.exercise([SUBMIT],policy,[critic()])
            self.assertTrue(r['submitted']);self.assertIsNone(r['official_success'])
            self.assertEqual(len(engine.environment.executed),int(policy.critic))
            self.assertEqual(r['interaction_rounds'],1+2*int(policy.critic))

    def test_protocol_repair_keeps_goal_and_consumes_original_request_budget(self):
        r,engine,events,actor,_=self.exercise([{'action':'run','argv':[]},run_action('cat','f.py'),SUBMIT])
        self.assertTrue(r['submitted']);self.assertEqual(r['tool_calls'],1)
        self.assertEqual(r['interaction_rounds'],3);self.assertEqual(r['mechanism_utilization']['protocol_errors'],1)
        self.assertIn('local_correction',json.dumps(actor.prompts[1]))
        self.assertEqual(len(engine.contrastive_failures),0)

    def test_syntax_error_is_corrected_without_failure_anchor(self):
        r,engine,events,_,_=self.exercise([run_action('syntax'),run_action('edit','fixed'),SUBMIT])
        self.assertTrue(r['submitted']);self.assertEqual(len(engine.contrastive_failures),0)
        self.assertEqual(r['routing']['stats']['execution_defects'],1)

    def test_reconnaissance_exemption_keeps_final_duplicate_guard(self):
        r,engine,events,_,_=self.exercise([run_action('cat','f.py'),run_action('cat','f.py'),SUBMIT])
        self.assertTrue(r['submitted']);self.assertEqual(r['tool_calls'],1)
        self.assertEqual(r['mechanism_utilization']['action_loop_blocks'],1)

    def test_active_orthogonality_does_not_block_new_information(self):
        original=RoutedTaskRunner._panel
        def panel(engine,*args,**kwargs):
            result=original(engine,*args,**kwargs)
            if not engine.contrastive_episode:engine._contrastive_activate('fixture')
            return result
        with patch.object(RoutedTaskRunner,'_panel',panel):
            r,_,_,_,_=self.exercise([run_action('cat','f.py'),SUBMIT])
        self.assertTrue(r['submitted']);self.assertEqual(r['mechanism_utilization'].get('contrastive_rejections',0),0)

    def test_critic_cannot_pass_from_prose_when_real_check_fails(self):
        env=StateEnvironment();env.value='bad';env.dependencies['f.py']='file:bad'
        r,engine,events,_,reviewer=self.exercise([SUBMIT,SUBMIT,SUBMIT],RoutingPolicy(critic=True),
                                              [critic(),critic()],env)
        self.assertTrue(r['submitted']);self.assertEqual(len(reviewer.prompts),4)
        self.assertEqual(r['routing']['critic_decision'],'partial_delivery_review_limit')
        self.assertFalse(any(e.get('accepted') for e in events if e['event']=='critic_review'))
        self.assertLessEqual(r['tool_calls'],2)

    def test_critic_gap_defers_delivery_even_when_check_passes(self):
        r,_,events,_,_=self.exercise([SUBMIT,SUBMIT],RoutingPolicy(critic=True),
            [critic('revise',['missing edge case']),critic()])
        self.assertTrue(r['submitted'])
        reviews=[e for e in events if e['event']=='critic_review']
        self.assertFalse(reviews[0]['accepted']);self.assertTrue(reviews[1]['accepted'])

    def test_critic_model_calls_and_checks_share_hard_limits(self):
        c=LeanConfig(max_turns=2,max_tools=1,subgoals_enabled=True,memory_decision=False)
        r,_,_,_,_=self.exercise([run_action('cat','f.py'),SUBMIT],RoutingPolicy(critic=True),[critic()],config=c)
        self.assertFalse(r['submitted']);self.assertEqual(r['tool_calls'],1)
        self.assertLessEqual(r['interaction_rounds'],2)

    def test_healthy_snapshot_created_only_after_real_subgoal_check(self):
        a=run_action('check',subgoal_plan=[goal()],subgoal_id='G1')
        r,engine,_,_,_=self.exercise([a,SUBMIT],RoutingPolicy(critic=True,backtracking=True),[critic()])
        self.assertEqual(r['routing']['stats']['healthy_snapshots'],1)
        self.assertEqual(r['mechanism_utilization']['checkpoints_created'],2)

    def test_regression_rollback_preserves_attempt_and_invalidates_proof(self):
        actions=[run_action('check',subgoal_plan=[goal()],subgoal_id='G1'),run_action('edit','bad1'),
                 run_action('check',subgoal_id='G1'),run_action('edit','bad2'),
                 run_action('check',subgoal_id='G1'),SUBMIT]
        r,engine,events,_,_=self.exercise(actions,RoutingPolicy(critic=True,backtracking=True),[critic()])
        self.assertEqual(r['routing']['stats']['rollbacks'],1)
        self.assertEqual(engine.environment.value,'seed')
        self.assertIn('bad2',engine.environment.saved.values())
        self.assertNotEqual(engine.subgoals.items['G1']['status'],'check_passed')
        self.assertIsNone(r['official_success'])

    def test_new_goal_failure_is_not_a_reason_to_rollback(self):
        env=StateEnvironment();env.value='bad';env.dependencies['f.py']='file:bad'
        r,engine,_,_,_=self.exercise([run_action('check',subgoal_plan=[goal()],subgoal_id='G1'),SUBMIT],
            RoutingPolicy(critic=True,backtracking=True),[critic()],env)
        self.assertEqual(r['routing']['stats'].get('rollbacks',0),0)
        self.assertEqual(r['routing']['stats'].get('healthy_snapshots',0),0)

    def test_automatic_rollback_defers_when_other_goal_work_changed_or_unknown(self):
        for other_state in ('file:new','unknown'):
            env=StateEnvironment();env.dependencies['other.py']='file:seed'
            other=dict(goal(),id='G2',targets=['other.py'])
            actions=[run_action('check',subgoal_plan=[goal(),other],subgoal_id='G1'),
                     run_action('edit','bad1'),run_action('check',subgoal_id='G1'),
                     run_action('edit','bad2'),run_action('check',subgoal_id='G1'),SUBMIT]
            original=env.execute
            def execute(action,deadline):
                result=original(action,deadline)
                if action['argv']==['edit','bad1']:env.dependencies['other.py']=other_state
                return result
            env.execute=execute
            r,engine,events,_,_=self.exercise(actions,RoutingPolicy(critic=True,backtracking=True),
                                            [critic()],env=env)
            self.assertEqual(r['routing']['stats'].get('rollbacks',0),0)
            self.assertEqual(r['routing']['stats']['rollback_protected_deferrals'],1)
            self.assertEqual(env.value,'bad2')
            self.assertTrue(any(e['event']=='rollback_deferred' and
                e.get('protected_paths')==['other.py'] for e in events))

if __name__=='__main__':unittest.main()
