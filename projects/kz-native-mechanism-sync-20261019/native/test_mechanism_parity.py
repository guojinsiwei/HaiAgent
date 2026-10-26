"""Offline behavior tests: original executor, scripted roles, no network/model API."""
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import solve
from native_repair import RepairRunner
from aligned_subgoals import AlignedLedger
from completion_alignment import basis, complete
from bestfgs.exploration_measurement import validate_measurement, measure
from bestfgs.exploration_trigger import check_identity, issue_identity, ExplorationTrigger
from bestfgs.verification_identity import verification_key, substantive_silent_check
from test_exploration_learning import active, action, observe, experiment
from test_native_repair import Scripted, goal


def evidence(eid='E1',code=0,output='CHECK_OK',**extra):
    result=dict(id=eid,return_code=code,stdout=output,stderr='',before='sha256:a',after='sha256:a',
        dependency_before={'check.py':'file:a'},dependency_after={'check.py':'file:a'},
        timed_out=False,blocked=False,capture_incomplete=False,terminal_projection_incomplete=False,
        execution_assessment=dict(execution_clean=code==0,check_status='unknown'))
    result.update(extra);return result


class Measurements(unittest.TestCase):
    def test_metric_types_complements_and_finite_values(self):
        for value in (None,[],True,float('nan'),float('inf')):
            e=experiment();e['supports']['value']=e['refutes']['value']=value
            with self.subTest(value=value),self.assertRaises(ValueError):validate_measurement(e)
        for field,value in [('op','eq'),('field','stderr'),('metric','other'),('value',1)]:
            e=experiment();e['refutes'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_measurement(e)

    def test_missing_conflicting_typed_and_incomplete_are_unknown(self):
        e=validate_measurement(experiment())
        for out in ('none','{"listeners":true}','{"listeners":null}','{"listeners":[]}','{"listeners":0}\n{"listeners":1}'):
            self.assertEqual(measure(e,{'stdout':out},True)['status'],'unknown')
        self.assertEqual(measure(e,{'stdout':'{"listeners":0}'},False)['reason'],'execution_unusable')

    def test_literal_observation_does_not_prove_hypothesis(self):
        e=validate_measurement(dict(hypothesis='x',supports=dict(field='stdout',contains='yes'),refutes=dict(field='stdout',contains='no')))
        r=measure(e,dict(stdout='yes'),True)
        self.assertEqual(r['status'],'unknown');self.assertEqual(r['reason'],'literal_observation_only')

    def test_metric_outcome_and_duplicate_identical_values(self):
        e=validate_measurement(experiment())
        self.assertEqual(measure(e,dict(stdout='{"listeners":1}\n{"listeners":1}'),True)['status'],'supported')
        self.assertEqual(measure(e,dict(stdout='{"listeners":0}'),True)['status'],'refuted')


class ExplorationParity(unittest.TestCase):
    def test_pytest_cosmetics_group_but_selection_and_cwd_do_not(self):
        self.assertEqual(check_identity('pytest -q test_a.py'),check_identity('python -m pytest -vv test_a.py --tb=short'))
        self.assertNotEqual(check_identity('pytest test_a.py -k a'),check_identity('pytest test_a.py -k b'))
        self.assertNotEqual(check_identity('pytest test_a.py','a'),check_identity('pytest test_a.py','b'))

    def test_issue_trigger_uses_goal_targets_diagnostic_family(self):
        focus=dict(goal='G1',targets=['parser.py']);row=dict(stderr='ValueError: a')
        self.assertEqual(issue_identity(focus,row),issue_identity(focus,dict(stderr='ValueError: b')))
        self.assertNotEqual(issue_identity(focus,row),issue_identity(dict(goal='G2',targets=['parser.py']),row))
        self.assertIsNone(issue_identity(focus,dict(stderr='error')))
        t=ExplorationTrigger();t.observe('check','E1','failed');t.observe('issue','E1','failed');t.observe('issue','E2','failed')
        self.assertEqual(t.pending(2)['key'],'issue')

    def test_monitor_triggers_on_two_complete_recent_observations(self):
        r=active();r._init_contrastive()
        review=dict(verdict='stalled',evidence_ids=['E1','E2'],next_check='measure the target')
        rows={i:evidence(i) for i in review['evidence_ids']}
        self.assertTrue(r._contrastive_monitor(review,rows));self.assertEqual(r.contrastive_failures,[])
        self.assertEqual(r.events[-1]['trigger_evidence']['reason'],'monitor_stalled_with_execution_evidence')
        self.assertEqual(rows['E1']['return_code'],0)

    def test_monitor_rejects_stale_incomplete_success_and_duplicate(self):
        for kind in ('stale','incomplete','passed','duplicate'):
            r=active();r._init_contrastive();rows={i:evidence(i) for i in ('E1','E2')}
            review=dict(verdict='stalled',evidence_ids=['E1','E2'],next_check='measure')
            if kind=='stale':rows['E20']=evidence('E20')
            if kind=='incomplete':rows['E2']['capture_incomplete']=True
            if kind=='passed':rows['E2']['execution_assessment']['check_status']='public_check_passed'
            if kind=='duplicate':review['evidence_ids']=['E1','E1']
            self.assertFalse(r._contrastive_monitor(review,rows),kind)

    def test_real_issue_outcomes_activate_across_commands(self):
        r=active();r._init_contrastive()
        r.subgoals=SimpleNamespace(active='G1',items={'G1':{'definition':{'targets':['main.py']}}})
        r.step('E1','python first.py',output='ValueError: first')
        r.step('E2','python second.py',output='ValueError: second')
        self.assertIsNotNone(r.contrastive_episode)
        self.assertIn('issue',r.contrastive_episode['trigger_key'])

    def test_measured_probe_may_share_vocabulary_and_uses_prior_result(self):
        r=active();a=action('gcc main.c -o main --boundary-probe');self.assertFalse((r._contrastive_before(a) or {}).get('not_executed'))
        observe(r,a);a=action('gcc main.c -o different')
        self.assertTrue(r._contrastive_before(a)['not_executed'])
        a['contrastive']['result_decision']=dict(result_id='XE3',action='revise',reason='use observed zero listeners')
        self.assertFalse(r._contrastive_before(a).get('not_executed',False));observe(r,a,'E4')
        self.assertTrue(any(e['event']=='exploration_result_used' for e in r.events))

    def test_sixteen_auxiliary_actions_close_gate(self):
        r=active()
        for i in range(16):r.step('E'+str(3+i),'cat file'+str(i),0,True)
        self.assertIsNone(r.contrastive_episode)
        self.assertEqual([e for e in r.events if e['event']=='contrastive_episode_end'][-1]['reason'],'episode_total_action_cap')

    def test_two_rejections_do_not_execute_diagnostic(self):
        r=active();a=action();del a['contrastive']
        r._contrastive_before(a);out=r._contrastive_before(a)
        self.assertTrue(out['not_executed']);self.assertNotIn('fallback_action',out);self.assertIsNone(r.contrastive_episode)

    def test_timeout_never_becomes_stable_failure_memory(self):
        r=active();before=len(r.contrastive_failures);a=action();r._contrastive_before(a)
        observe(r,a,return_code=124,timed_out=True)
        self.assertEqual(len(r.contrastive_failures),before)

    def test_disabled_still_disables_monitor_exploration(self):
        r=active();r.config.contrastive_mode='off'
        self.assertFalse(r._contrastive_monitor(dict(verdict='stalled'),{}))


class Goals(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.ledger=AlignedLedger(self.root,lambda *a,**k:None)

    def test_register_before_check_then_explicit_revision(self):
        g=goal();g['verification']=None
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_plan=[g]))
        self.assertEqual(self.ledger.items['G1']['status'],'pending')
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_update=dict(id='G1',expected_revision=1,reason='found public checker',verification=goal()['verification'])))
        self.assertEqual(self.ledger.items['G1']['revision'],2)
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_update=dict(id='G1',expected_revision=1,reason='stale',title='bad')))
        self.assertEqual(self.ledger.items['G1']['revision'],2);self.assertIn('Stale',self.ledger.notices[0])

    def test_substantive_silent_tests_and_trivial_controls(self):
        for argv in (['python','-m','doctest','checks.txt'],['pytest','test_x.py'],['node','--test']):
            self.assertTrue(substantive_silent_check(dict(argv=argv)))
        for argv in (['echo','ok'],['python','-m','pytest','--collect-only'],['ctest','-N'],['make','test','-n']):
            self.assertFalse(substantive_silent_check(dict(argv=argv)))
        g=goal();g['verification']=dict(argv=['python','-m','doctest','checks.txt'],stdout_contains=[],exit_code=0)
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_plan=[g]))
        self.assertIsNotNone(self.ledger.items['G1']['definition']['verification'])

    def test_matching_receipt_auto_advances_and_failure_revokes(self):
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_plan=[goal()]))
        cmd=dict(action='run',argv=['python3','check.py']);row=evidence()
        self.ledger.observe(None,cmd,row,row['execution_assessment'])
        self.assertEqual(self.ledger.items['G1']['status'],'check_passed')
        row=evidence('E2',1);self.ledger.observe(None,cmd,row,row['execution_assessment'])
        self.assertEqual(self.ledger.items['G1']['status'],'needs_work')

    def test_definition_change_invalidates_proof(self):
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_plan=[goal()]))
        cmd=dict(action='run',argv=['python3','check.py']);row=evidence()
        self.ledger.observe(None,cmd,row,row['execution_assessment'])
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_update=dict(id='G1',reason='new requirement',acceptance='new acceptance')))
        self.assertIsNone(self.ledger.items['G1']['proof']);self.assertEqual(len(self.ledger.items['G1']['history']),1)

    def test_verify_identity_ignores_description_but_retains_inputs_and_limits(self):
        a=dict(argv=['python','check.py'],cwd='/app',purpose='first')
        self.assertEqual(verification_key(a),verification_key(dict(a,purpose='second')))
        self.assertEqual(verification_key(a),verification_key(dict(argv=['bash','-lc','cd /app && python check.py'])))
        for changed in (dict(a,stdin='different'),dict(a,cwd='/else'),dict(a,timeout_seconds=20),dict(a,env={'X':'1'})):
            self.assertNotEqual(verification_key(a),verification_key(changed))
        self.assertNotEqual(verification_key(a),verification_key(dict(argv=['bash','-lc','cd /app/link/.. && python check.py'])))

    def test_binding_rejects_superseded_or_changed_receipt(self):
        self.ledger.begin(dict(action='run',argv=['ls'],subgoal_plan=[goal()]))
        cmd=dict(action='run',argv=['python3','check.py']);old=evidence(command=cmd);new=evidence('E2',1,command=cmd)
        with self.assertRaises(ValueError):self.ledger.bind('G1','E1',{'E1':old,'E2':new},{'check.py':'file:a'})
        with self.assertRaises(ValueError):self.ledger.bind('G1','E1',{'E1':old},{'check.py':'file:b'})
        self.ledger.bind('G1','E1',{'E1':old},{'check.py':'file:a'})
        self.assertEqual(self.ledger.items['G1']['status'],'check_passed')


class Completion(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.work=self.root/'work';self.work.mkdir()
        (self.work/'check.py').write_text('assert 2+2==4\nprint("CHECK_OK")\n')

    def review(self):
        check=dict(argv=[sys.executable,'check.py'],stdout_contains=['CHECK_OK'],requirement_quotes=['Check addition.'],gap_ids=[],
                   provenance=dict(author='fixture',kind='public_spec',expected_rule='Check addition.',independence='assert arithmetic',sources=[dict(kind='task',quote='Check addition.')]))
        return dict(decision='accept',requirements=['Check addition.'],gaps=[],checks=[check])

    def engine(self,actions,critic,tools=10):
        runner=RepairRunner(solve.InPlace(self.work,self.root/('state'+str(len(list(self.root.iterdir()))))),Scripted(actions),Scripted([]),
            solve.LeanConfig(max_turns=20,max_tools=tools,wall_seconds=120,memory_reliability=True,outcome_reliability=True,subgoals_enabled=True),
            self.root/'trace',routing=solve.RoutingPolicy(critic=True,critic_limit=20),critic_client=Scripted(critic))
        return runner

    def test_actual_native_executor_accepts_grounded_receipt_and_counts_roles(self):
        verdict=dict(decision='accept',requirements=['Check addition.'],gaps=[],checks=[],requirement_evidence=[dict(requirement_quote='Check addition.',evidence_ids=['E1'],reason='actual assertion ran')])
        runner=self.engine([dict(action='submit',summary='done')],[self.review(),verdict])
        result=runner.run(solve.TaskSpec('fixture','Check addition.'))
        self.assertTrue(result['submitted'],result);self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['interaction_rounds'],3);self.assertIsNone(result['official_success'])

    def test_repeated_submission_without_activity_does_not_buy_review(self):
        plan=dict(decision='revise',requirements=['Check addition.'],gaps=['missing checker'],checks=[],reason_kind='repair_check',next_step='prepare a check')
        runner=self.engine([dict(action='submit',summary='one'),dict(action='submit',summary='reworded')],[plan])
        result=runner.run(solve.TaskSpec('fixture','Check addition.'))
        self.assertFalse(result['submitted']);self.assertEqual(result['stop_reason'],'incomplete_repeated_submission')
        self.assertEqual(runner.critic_rounds,1);self.assertEqual(result['tool_calls'],0)

    def test_fabricated_basis_and_coverage_cannot_accept(self):
        plan=self.review();plan['checks'][0]['provenance']['sources'][0]['quote']='fabricated quote'
        verdict=dict(decision='accept',requirements=['Check addition.'],gaps=[],checks=[],requirement_evidence=[dict(requirement_quote='Check addition.',evidence_ids=['E1'],reason='claim')])
        runner=self.engine([dict(action='submit',summary='one'),dict(action='submit',summary='two')],[plan,verdict])
        result=runner.run(solve.TaskSpec('fixture','Check addition.'))
        self.assertFalse(result['submitted']);self.assertEqual(runner.critic_decision,'needs_revision')

    def test_gap_requires_targeted_fresh_grounded_closure(self):
        runner=self.engine([],[]);runner.task=solve.TaskSpec('fixture','Check addition.')
        gap=runner._gap('test','missing proof',proof_obligation='correctness_basis')
        update=dict(gap_id=gap['id'],status='closed',evidence_ids=['E1'],reason='actual check')
        receipt=dict(evidence_id='E1',passed=True,gap_ids=[],basis=dict(level='attributed_correctness_basis'),reused_current_receipt=False,command_key='a')
        runner._close_gaps(dict(gap_updates=[update]),[receipt],[evidence()]);self.assertEqual(gap['status'],'open')
        receipt['gap_ids']=[gap['id']];receipt['reused_current_receipt']=True
        runner._close_gaps(dict(gap_updates=[update]),[receipt],[evidence()]);self.assertEqual(gap['status'],'open')
        receipt['reused_current_receipt']=False
        runner._close_gaps(dict(gap_updates=[update]),[receipt],[evidence()]);self.assertEqual(gap['status'],'closed')
        runner.completion_checks['a']='E2';runner._sync_completion({'check.py':'file:a'},runner.environment.scope())
        self.assertEqual(gap['status'],'needs_reverification')

    def test_intervening_observation_survives_A_B_A(self):
        runner=self.engine([],[]);runner.subgoals=None;runner.task=solve.TaskSpec('fixture','Check addition.')
        runner.completion_history.add('A');a=runner._token();runner.completion_history.add('B');runner.completion_history.add('A')
        self.assertNotEqual(a,runner._token());self.assertEqual(len(runner.completion_history),2)

    def test_unknown_receipt_never_becomes_proof(self):
        self.assertFalse(complete(evidence(timed_out=True)))

    def test_invalid_optional_review_protocol_is_recoverable(self):
        for field in ('gap_updates','new_gaps','requirement_evidence'):
            runner=self.engine([],[])
            with self.assertRaises(ValueError):runner._register(dict(gaps=[],**{field:None}))

    def test_cache_requires_scope_no_intervening_observation_and_fresh_override(self):
        runner=self.engine([],[]);runner.subgoals=None
        runner.counts={'tool_calls':0};calls=[]
        row=evidence();row['before']=row['after']=runner.environment.scope()
        row['dependency_before']=row['dependency_after']=runner.environment.dependency_state(['check.py'])
        def run(cmd,**kw):
            calls.append(cmd);runner.counts['tool_calls']+=1
            runner.last_tool_observation={'evidence':dict(row,id='E'+str(runner.counts['tool_calls']))}
            return {}
        runner._run_command=run
        cmd=dict(action='run',argv=['cat','check.py']);check=dict(stdout_contains=['CHECK_OK'],requirement_quotes=['Check addition.'],cache_scope='workspace')
        first=runner._receipt(cmd,check,{})[0];second=runner._receipt(cmd,check,{})[0]
        self.assertFalse(first['reused_current_receipt']);self.assertTrue(second['reused_current_receipt'])
        runner.counts['tool_calls']+=1
        self.assertFalse(runner._receipt(cmd,check,{})[0]['reused_current_receipt'])
        self.assertFalse(runner._receipt(cmd,dict(check,fresh=True),{})[0]['reused_current_receipt'])
        (self.work/'check.py').write_text('changed')
        self.assertFalse(runner._receipt(cmd,check,{})[0]['reused_current_receipt'])

    def test_actual_monitor_hook_starts_exploration_without_faking_failure(self):
        monitor=Scripted([dict(verdict='stalled',reason='two observations leave the task unresolved',evidence_ids=['E1','E2'],next_check='measure the relevant boundary',memories=[])])
        actions=[dict(action='run',argv=[sys.executable,'-c','print(1)']),dict(action='run',argv=[sys.executable,'-c','print(2)']),dict(action='submit',summary='partial')]
        runner=RepairRunner(solve.InPlace(self.work,self.root/'monitor-state'),Scripted(actions),Scripted([dict(alternatives=[])]),
            solve.LeanConfig(max_turns=12,max_tools=10,wall_seconds=120,semantic_monitor=True,monitor_cooldown_tools=2,monitor_interval_tools=2,max_monitor_calls=1,
                             contrastive_mode='orthogonal',contrastive_predictions=False,memory_decision=False,memory_reliability=True,outcome_reliability=True),
            self.root/'monitor-trace',routing=solve.RoutingPolicy(critic=False),monitor_client=monitor)
        result=runner.run(solve.TaskSpec('fixture','Check addition.'))
        self.assertTrue(result['submitted'],result);self.assertEqual(runner.counts['contrastive_episodes'],1)
        self.assertEqual(runner.contrastive_failures,[])
        self.assertEqual(runner.counts['monitor_calls'],1)


class PreservedMechanisms(unittest.TestCase):
    def test_memory_evidence_relevance_and_dependency_freshness(self):
        from bestfgs.lean_memory import Memories
        memories=Memories(reliable=True);row=evidence();row['stable_dependencies']={'check.py':'file:a'}
        draft=dict(kind='blocker',conclusion='parser requires input',condition='empty parser input',targets=['check.py'],evidence_ids=['E1'])
        item,_=memories.admit(draft,{'E1':row},{'E1'},lambda p:{k:'file:a' for k in p},current_scope='sha256:a')
        self.assertEqual(memories.recall('unrelated zebra','sha256:a',{'check.py':'file:a'}),[])
        self.assertIn('changed_or_unknown',memories.recall('parser','sha256:b',{'check.py':'file:b'})[0]['applicability'])
        with self.assertRaises(ValueError):memories.admit(dict(draft,evidence_ids=['E99']),{'E1':row},{'E1'},lambda p:{})
        other=Memories(reliable=True);self.assertFalse(other.items)

    def test_memory_reserved_context_and_review_coverage(self):
        from bestfgs.memory_injection import reserved_view,validate_review
        record=dict(id='M1',kind='blocker',conclusion='observed failure',condition='unchanged source',evidence_ids=['E1'])
        shown,omitted=reserved_view([record],1000)
        self.assertEqual(shown[0]['conclusion'],'observed failure');self.assertFalse(omitted)
        with self.assertRaises(ValueError):reserved_view([record],1)
        review=dict(ids=['M1'],observed_result='failed',applicability='same input',decision='recheck',reason='inspect condition')
        value=dict(memory_review=review,strategy_adjustment='inspect missing premise',action='run',argv=['cat','check.py'])
        self.assertEqual(validate_review(value,{'M1'},True)['decision'],'recheck')
        with self.assertRaises(ValueError):validate_review(dict(value,memory_review=dict(review,ids=['M2'])),{'M1'},True)
        with self.assertRaises(ValueError):validate_review(value,{'M1','M2'},True,required_ids={'M2'})

    def test_terminal_projection_preserves_earlier_errors_and_marks_partial(self):
        from bestfgs.terminal_text import project_terminal
        view,meta=project_terminal('ERROR\rOK\x1b[2J')
        self.assertIn('ERROR',view);self.assertIn('OK',view)
        self.assertTrue(project_terminal('partial\x1b[')[1]['incomplete'])

    def test_history_retrieval_preserves_original_and_is_task_local(self):
        from bestfgs.lean_conversation import Conversation
        history=Conversation();history.append(dict(action='run',argv=['cat','a']),dict(stdout='exact old observation'))
        self.assertIn('exact old observation',history.retrieve(dict(turn_ids=[1]))['history_records'][0]['text'])
        self.assertFalse(Conversation().turns)


if __name__=='__main__':unittest.main(verbosity=2)
