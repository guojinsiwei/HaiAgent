"""Zero API: independent ledger and actual DH action loop acceptance."""
from copy import deepcopy
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.subgoals import SubgoalLedger,definition
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec,CommandSpec,CommandResult
from test_lean import FakeEnvironment,Scripted,run_action,SUBMIT

def goal(key='G1',deps=(),path='f.py'):
    return {'id':key,'title':'Check parser '+key,'acceptance':'Parser preserves the required value',
            'depends_on':list(deps),'targets':[path],
            'verification':{'argv':['read'],'stdout_contains':['seed']}}

def view(eid='E1',**overrides):
    row=dict(id=eid,before='s1',after='s1',return_code=0,stdout='seed',
        timed_out=False,blocked=False,capture_incomplete=False,terminal_projection_incomplete=False,
        dependency_before={'f.py':'file:old'},dependency_after={'f.py':'file:old'})
    row.update(overrides);return row

class LedgerTests(unittest.TestCase):
    def setUp(self):self.ledger=SubgoalLedger()
    def define(self,*rows):self.ledger.begin(run_action('read',subgoal_plan=list(rows)))
    def check(self,key='G1',**overrides):
        action=run_action('read',subgoal_id=key,subgoal_phase='verify')
        attempt=self.ledger.begin(action)
        self.ledger.observe(attempt,action,view(**overrides),{'execution_clean':True})

    def test_no_completion_from_declaration_or_ordinary_exit_zero(self):
        self.define(goal());action=run_action('inspect',subgoal_id='G1')
        self.ledger.observe(self.ledger.begin(action),action,view(),{'execution_clean':True})
        self.assertEqual(self.ledger.items['G1']['status'],'pending')
        with self.assertRaises(ValueError):self.ledger.begin(dict(SUBMIT,subgoal_update={'id':'G1','status':'completed','reason':'trust me'}))
        self.assertEqual(self.ledger.items['G1']['status'],'pending')

    def test_success_is_only_declared_check_and_retains_evidence(self):
        self.define(goal());self.check()
        row=self.ledger.items['G1'];self.assertEqual(row['status'],'check_passed')
        self.assertEqual(row['proof']['evidence_id'],'E1')
        self.assertIsNone(self.ledger.snapshot()['task_success'])

    def test_matching_declared_check_does_not_need_redundant_verify_command(self):
        self.define(goal());a=run_action('read',subgoal_id='G1')
        self.ledger.observe(self.ledger.begin(a),a,view(),{'execution_clean':True})
        self.assertEqual(self.ledger.items['G1']['status'],'check_passed')

    def test_failure_and_incomplete_capture_never_pass(self):
        cases=[{'return_code':1},{'stdout':'no marker'},{'timed_out':True},{'blocked':True},
               {'capture_incomplete':True},{'terminal_projection_incomplete':True},
               {'dependency_after':{'f.py':'unknown'}},{'dependency_after':{'f.py':'link:any'}},
               {'dependency_after':{'f.py':'file:changed'}}]
        for case in cases:
            with self.subTest(case=case):
                self.ledger=SubgoalLedger();self.define(goal());self.check(**case)
                self.assertEqual(self.ledger.items['G1']['status'],'needs_work')

    def test_masked_failure_assessment_prevents_passing(self):
        self.define(goal());a=run_action('read',subgoal_id='G1',subgoal_phase='verify')
        self.ledger.observe(self.ledger.begin(a),a,view(),{'execution_clean':False})
        self.assertEqual(self.ledger.items['G1']['status'],'needs_work')

    def test_unknown_or_cyclic_dependencies_are_atomic(self):
        for rows in ([goal(deps=['G2'])],[goal(deps=['G2']),goal('G2',deps=['G1'])]):
            with self.assertRaises(ValueError):self.define(*rows)
            self.assertEqual(self.ledger.items,{})

    def test_immutable_criterion_cannot_be_weakened(self):
        self.define(goal());original=self.ledger.snapshot()
        g=goal();g['acceptance']='anything is fine'
        with self.assertRaises(ValueError):self.define(goal('G2'),g)
        self.assertEqual(self.ledger.snapshot(),original)

    def test_prerequisite_order_and_propagated_invalidation(self):
        self.define(goal(),goal('G2',deps=['G1']))
        self.assertEqual(self.ledger.view()['ready'],['G1'])
        self.check('G2');self.assertEqual(self.ledger.items['G2']['status'],'needs_work')
        self.check('G1');self.check('G2');self.assertEqual(self.ledger.items['G2']['status'],'check_passed')
        self.ledger.begin(dict(SUBMIT,subgoal_update={'id':'G1','status':'blocked','reason':'dependency suspect'}))
        self.assertEqual(self.ledger.items['G2']['status'],'needs_recheck')

    def test_related_edit_invalidates_but_unrelated_edit_does_not(self):
        self.define(goal());self.check()
        self.ledger.sync('changed',{'f.py':'file:old','notes.txt':'file:new'})
        self.assertEqual(self.ledger.items['G1']['status'],'check_passed')
        self.ledger.sync('changed_again',{'f.py':'file:new'})
        self.assertEqual(self.ledger.items['G1']['status'],'needs_recheck')

    def test_restore_never_resurrects_historical_pass(self):
        self.define(goal());self.check();self.ledger.sync('s1',{'f.py':'file:old'},restored=True)
        self.assertEqual(self.ledger.items['G1']['status'],'needs_recheck')
        self.ledger.sync('s1',{'f.py':'file:old'})
        self.assertEqual(self.ledger.items['G1']['status'],'needs_recheck')

    def test_exact_check_command_cwd_and_stdin_are_required(self):
        self.define(goal())
        for extra in ({'argv':['echo','seed']},{'cwd':'other'},{'stdin':'new'}):
            with self.assertRaises(ValueError):self.ledger.begin(dict(run_action('read',subgoal_id='G1',subgoal_phase='verify'),**extra))

    def test_stale_attempt_cannot_count_diagnostic_or_other_action(self):
        self.define(goal());a=run_action('read',subgoal_id='G1',subgoal_phase='verify')
        attempt=self.ledger.begin(a)
        self.ledger.observe(attempt,run_action('different'),view(),{'execution_clean':True})
        self.assertEqual(self.ledger.items['G1']['attempts'],0)

    def test_capacity_never_evicts_unresolved_goals_and_panel_is_bounded(self):
        for group in range(3):
            rows=[]
            for i in range(group*4+1,group*4+5):
                g=goal('G'+str(i));g['title']='题'*100;g['acceptance']='验'*240
                g['verification']['argv']=['python','-c','x'*700]
                rows.append(g)
            self.define(*rows)
        self.ledger.begin(run_action('read',subgoal_id='G12'))
        self.assertLessEqual(len(json.dumps(self.ledger.view(),ensure_ascii=False)),3500)
        with self.assertRaises(ValueError):self.define(goal('G13'))
        self.assertEqual(len(self.ledger.items),12)

    def test_dependency_unblocking_priority_is_not_just_definition_order(self):
        self.define(goal(),goal('G2'),goal('G3',deps=['G2']),goal('G4',deps=['G3']))
        self.assertEqual(self.ledger.view()['suggested_next'],'G2')
        self.ledger.begin(run_action('read',subgoal_id='G1'))
        self.assertEqual(self.ledger.view()['suggested_next'],'G1')

    def test_invalid_paths_types_or_missing_assertions_are_rejected(self):
        variants=[dict(goal(),targets=['../secret']),dict(goal(),targets=[]),dict(goal(),depends_on=[{}]),
            dict(goal(),verification={'argv':['true'],'stdout_contains':[]}),dict(goal(),id=[])]
        for g in variants:
            with self.subTest(g=g),self.assertRaises(ValueError):definition(g)


class RunnerTests(unittest.TestCase):
    def exercise(self,actions,enabled=True,env=None,**overrides):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        env=env or FakeEnvironment();env.dependencies={'f.py':'file:old'}
        actor=Scripted(actions);advisor=Scripted([])
        options=dict(subgoals_enabled=enabled,memory_decision=False,memory_injection=False,
                     max_turns=40,max_tools=30,diagnostic_advisor_threshold=100,repeated_failure_threshold=100)
        options.update(overrides)
        runner=LeanTaskRunner(env,actor,advisor,LeanConfig(**options),Path(tmp.name)/'audit')
        result=runner.run(TaskSpec('fixture','Implement the public parser requirement'))
        self.assertIsNone(result['error_type'],result)
        events=read_trace(Path(tmp.name)/'audit/events.jsonl')
        return result,runner,actor,events

    def test_full_define_work_check_submit_flow_without_added_calls(self):
        actions=[run_action('inspect',subgoal_plan=[goal()],subgoal_id='G1'),
                 run_action('read',subgoal_id='G1',subgoal_phase='verify'),SUBMIT]
        result,runner,actor,events=self.exercise(actions)
        self.assertEqual(result['interaction_rounds'],3);self.assertEqual(result['tool_calls'],2)
        self.assertEqual(result['advisor_rounds'],0)
        self.assertEqual(result['subgoal_summary']['goals']['G1']['status'],'check_passed')
        self.assertEqual(actor.prompts[-1]['fixed_context']['subgoals']['goals'][0]['status'],'check_passed')
        self.assertEqual(next(e for e in events if e['event']=='method_end')['result'],result)
        self.assertTrue((runner.output/'subgoals.json').exists())

    def test_feature_off_has_no_subgoal_prompt_counters_or_artifact(self):
        result,runner,actor,events=self.exercise([run_action('read',subgoal_plan=[goal()]),SUBMIT],enabled=False)
        self.assertNotIn('subgoal_summary',result)
        self.assertFalse(any('subgoals' in p['fixed_context'] for p in actor.prompts))
        self.assertFalse((runner.output/'subgoals.json').exists())
        self.assertFalse(any(e['event'].startswith('subgoal_') for e in events))

    def test_bad_metadata_does_not_stop_valid_tools_or_accumulate_protocol_errors(self):
        bad=run_action('read',subgoal_plan=[goal(deps=['G9'])])
        result,runner,actor,events=self.exercise([bad]*5+[SUBMIT])
        self.assertTrue(result['submitted']);self.assertEqual(result['tool_calls'],5)
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],0)
        self.assertEqual(result['mechanism_utilization']['subgoal_metadata_ignored'],5)
        self.assertTrue(actor.prompts[1]['fixed_context']['subgoals']['notices'])

    def test_unresolved_goals_never_block_submission(self):
        result,runner,_,_=self.exercise([run_action('inspect',subgoal_plan=[goal()],subgoal_id='G1'),SUBMIT])
        self.assertTrue(result['submitted']);self.assertEqual(result['subgoal_summary']['unresolved'],['G1'])

    def test_edit_invalidates_achieved_goal_before_submission(self):
        result,_,actor,_=self.exercise([run_action('read',subgoal_plan=[goal()],subgoal_id='G1',subgoal_phase='verify'),
            run_action('artifact','f.py','new'),SUBMIT])
        self.assertEqual(result['subgoal_summary']['goals']['G1']['status'],'needs_recheck')
        self.assertEqual(actor.prompts[-1]['fixed_context']['subgoals']['goals'][0]['status'],'needs_recheck')

    def test_restore_requires_recheck(self):
        result,_,_,_=self.exercise([run_action('read',subgoal_plan=[goal()],subgoal_id='G1',subgoal_phase='verify'),
            dict(action='restore',checkpoint_id='C1',reason='try original state'),SUBMIT])
        self.assertEqual(result['subgoal_summary']['goals']['G1']['status'],'needs_recheck')

    def test_gate_rejection_does_not_count_as_verification(self):
        result,_,_,_=self.exercise([run_action('read'),
            run_action('read',subgoal_plan=[goal()],subgoal_id='G1',subgoal_phase='verify'),SUBMIT],
            contrastive_mode='orthogonal',contrastive_predictions=False,memory_reliability=True,outcome_reliability=True)
        row=result['subgoal_summary']['goals']['G1']
        self.assertEqual(result['tool_calls'],1);self.assertEqual(row['checks'],0)
        self.assertNotEqual(row['status'],'check_passed')

    def test_mode_enabled_is_task_local_and_does_not_touch_hai(self):
        _,first,_,_=self.exercise([run_action('read',subgoal_plan=[goal()]),SUBMIT])
        result,second,_,_=self.exercise([SUBMIT])
        self.assertEqual(len(first.subgoals.items),1);self.assertFalse(second.subgoals.items)
        self.assertEqual(result['version'],'DH-subgoal-v1')

    def test_subgoal_rename_is_not_a_new_executable_for_memory(self):
        a=run_action('read',subgoal_id='G1');b=run_action('read',subgoal_id='G2')
        self.assertEqual(LeanTaskRunner._action_core(a),LeanTaskRunner._action_core(b))

    def test_enabled_boolean_is_strict(self):
        for value in (1,'yes',None):
            with self.assertRaises(ValueError):LeanConfig(subgoals_enabled=value)

    def test_full_ledger_fits_small_context_without_new_calls(self):
        actions=[]
        for group in range(3):
            rows=[]
            for i in range(group*4+1,group*4+5):
                g=goal('G'+str(i));g['title']='标题'*50;g['acceptance']='标准'*120
                rows.append(g)
            actions.append(run_action('inspect',subgoal_plan=rows,subgoal_id=rows[0]['id']))
        result,_,actor,_=self.exercise(actions+[SUBMIT],context_chars=16000)
        self.assertTrue(result['submitted']);self.assertEqual(result['interaction_rounds'],4)
        self.assertEqual(len(actor.prompts[-1]['fixed_context']['subgoals']['goals']),12)

    def test_real_python_failure_repair_verification_uses_same_three_tool_calls(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        workspace=Path(tmp.name);(workspace/'f.py').write_text('bad',encoding='utf-8')
        class RealEnvironment(FakeEnvironment):
            def scope(self):return hashlib.sha256((workspace/'f.py').read_bytes()).hexdigest()
            def dependency_state(self,paths):
                return {p:'file:'+hashlib.sha256((workspace/p).read_bytes()).hexdigest() if (workspace/p).is_file() else 'missing' for p in paths}
            def execute(self,action,deadline):
                self.executed.append(action)
                # Only these deterministic fixtures run, never a model-generated process.
                p=subprocess.run(action['argv'],cwd=workspace,capture_output=True,text=True,
                                 timeout=10,env={'SYSTEMROOT':'C:/Windows'} if sys.platform=='win32' else {})
                return CommandResult(CommandSpec(tuple(action['argv']),'public fixture'),p.returncode,p.stdout,p.stderr,0)
        check=[sys.executable,'-B','-c',"from pathlib import Path; assert Path('f.py').read_text()=='good'; print('parser checks passed')"]
        edit=[sys.executable,'-B','-c',"from pathlib import Path; Path('f.py').write_text('good')"]
        g=goal();g['verification']={'argv':check,'stdout_contains':['parser checks passed']}
        result,_,_,events=self.exercise([
            run_action(*check,subgoal_plan=[g],subgoal_id='G1',subgoal_phase='verify'),
            run_action(*edit,subgoal_id='G1'),run_action(*check,subgoal_id='G1',subgoal_phase='verify'),SUBMIT],env=RealEnvironment())
        self.assertEqual(result['subgoal_summary']['goals']['G1']['status'],'check_passed')
        self.assertEqual(result['tool_calls'],3);self.assertEqual(result['interaction_rounds'],4)
        checks=[e['event'] for e in events if e['event'] in {'subgoal_check_passed','subgoal_check_not_passed'}]
        self.assertEqual(checks,['subgoal_check_not_passed','subgoal_check_passed'])

if __name__=='__main__':unittest.main()
