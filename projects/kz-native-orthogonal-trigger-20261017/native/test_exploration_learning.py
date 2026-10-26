import unittest
from types import SimpleNamespace
from test_exploration_trigger import Runner
from bestfgs.exploration_learning import select_anchors,validate_experiment,recall_results
from bestfgs.contrastive_exploration import command_text,validate_orthogonal
from bestfgs.lean_memory import action_key

def experiment():return dict(hypothesis='service listens locally',supports=dict(field='stdout',contains='LISTEN'),refutes=dict(field='stdout',contains='NO_SOCKET'))
def action(command='ss -lnt'):
    a=dict(action='run',argv=['bash','-lc',command],cwd='/app',purpose='inspect listener')
    a['contrastive']=dict(negative_anchors_summary='connection failed',proposed_strategy='inspect listener',
        orthogonality_proof=dict(dependency_dimension='same environment',target_dimension='inspect sockets',command_dimension='same shell'),
        changed_dimensions=['target_dimension'],exploration=experiment(),final_command=command)
    return a
def active():
    r=Runner();r.config.contrastive_threshold=0.8;r.environment=SimpleNamespace(dependency_state=lambda p:{x:'file:a' for x in p});r._action_core=lambda a:a
    r.step('E1');r.step('E2');r._contrastive_context('a',{})
    return r
def observe(r,a,eid='E3',stdout='NO_SOCKET',**extra):
    r.counts['tool_calls']+=1
    row=dict(id=eid,return_code=0,stdout=stdout,stderr='',before='a',after='a',category='generic',
             timed_out=False,blocked=False,capture_incomplete=False,terminal_projection_incomplete=False,dependency_after={})
    row.update(extra)
    r._contrastive_outcome(a,row,dict(execution_clean=row['return_code']==0,check_status='unknown'))
    return row

class Tests(unittest.TestCase):
    def test_real_runner_injects_result_in_next_solver_prompt(self):
        import sys,tempfile
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).parent/'legacy/sources/bestfgs-project/tests'))
        from test_lean import LeanTests,LeanConfig,run_action,SUBMIT,FakeEnvironment
        temp=Path(__file__).resolve().parents[3]/'experiment_records/orthogonal-learning-20261017/test-tmp'
        temp.mkdir(exist_ok=True);previous=tempfile.tempdir;tempfile.tempdir=str(temp)
        fixture=LeanTests();env=FakeEnvironment();env.value='NO_SOCKET'
        try:
            result,events,actor,_,env,runner=fixture.exercise([run_action('fail'),run_action('fail'),action(),SUBMIT],env=env,
                config=LeanConfig(max_turns=4,max_tools=10,contrastive_mode='orthogonal',contrastive_predictions=False,
                    memory_reliability=True,outcome_reliability=True,memory_decision=False))
            self.assertEqual(len(env.executed),2)
            self.assertEqual(actor.prompts[-1]['fixed_context']['contrastive_exploration']['exploration_results'][0]['status'],'refuted')
            self.assertEqual(len([e for e in events if e['event']=='exploration_learning']),1)
        finally:fixture.doCleanups();tempfile.tempdir=previous
    def test_anchors_rank_trigger_and_merge_routes(self):
        rows=[dict(id='F'+str(i),evidence_id='E'+str(i),check_key=k,command='compile',observation='failed',scope='a') for i,k in [(1,'a'),(2,'a'),(3,'b')]]
        selected=select_anchors(rows,trigger_key='a')
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['attempts'],2)
        self.assertEqual(selected[0]['evidence_ids'],['E1','E2'])
    def test_one_dimension_and_required_prediction(self):
        a=action();validate_orthogonal(a,[],0.8)
        a['contrastive']['changed_dimensions']=[]
        with self.assertRaises(ValueError):validate_orthogonal(a,[],0.8)
        p=experiment();p['refutes']=p['supports']
        with self.assertRaises(ValueError):validate_experiment(p)
    def test_real_before_outcome_context_loop(self):
        r=active();a=action();r._contrastive_before(a);observe(r,a)
        record=r.exploration_results[0]
        self.assertEqual(record['status'],'refuted');self.assertEqual(record['evidence_id'],'E3')
        self.assertEqual(record['evidence'],[dict(field='stdout',quote='NO_SOCKET')])
        panel=r._contrastive_context('a',{})
        self.assertEqual(panel['exploration_results'][0]['status'],'refuted')
        self.assertFalse(record['semantic_verified']);self.assertIsNone(record['task_success'])
        self.assertIn('exploration-results.json',r.saved)
    def test_unknown_for_both_neither_incomplete_and_timeout(self):
        for stdout,extra in [('LISTEN NO_SOCKET',{}),('other',{}),('NO_SOCKET',dict(capture_incomplete=True)),('NO_SOCKET',dict(timed_out=True))]:
            with self.subTest(stdout=stdout,extra=extra):
                r=active();a=action();r._contrastive_before(a);observe(r,a,stdout=stdout,**extra)
                self.assertEqual(r.exploration_results[0]['status'],'unknown')
    def test_support_retains_observation_not_success(self):
        r=active();a=action();r._contrastive_before(a);observe(r,a,stdout='LISTEN')
        self.assertEqual(r.exploration_results[0]['status'],'supported');self.assertIsNone(r.exploration_results[0]['task_success'])
    def test_auxiliary_tools_do_not_exhaust_probe_allowance(self):
        r=active();r.config.contrastive_episode_tools=2
        for i in range(25):r.step('read'+str(i),'cat main.c',0,True)
        self.assertIsNotNone(r.contrastive_episode);self.assertEqual(r.contrastive_episode['probes'],0)
        a=action();r._contrastive_before(a);observe(r,a)
        self.assertIsNotNone(r.contrastive_episode)
        a=action('inspect-service-config');r._contrastive_before(a);observe(r,a,'E4')
        self.assertIsNone(r.contrastive_episode);self.assertEqual(len(r.exploration_results),2)
    def test_duplicate_and_mismatch_cannot_fabricate_a_lesson(self):
        r=active();a=action();r._contrastive_before(a);observe(r,action('different'))
        self.assertEqual(r.exploration_results,[])
        r._contrastive_before(a);observe(r,a,'E4');observe(r,a,'E4')
        self.assertEqual(len(r.exploration_results),1)
    def test_condition_change_and_conflicts_preserve_history(self):
        r=active();a=action();r._contrastive_before(a);observe(r,a)
        a=action('inspect-service-config');r._contrastive_before(a);observe(r,a,'E4',stdout='LISTEN',before='b',after='b')
        panel=r._contrastive_context('b',{})
        self.assertEqual([x['status'] for x in panel['exploration_results']],['supported','refuted'])
        self.assertEqual(panel['exploration_results'][1]['applicability'],'historical_conditions_recheck')
    def test_real_routed_readonly_probe_and_syntax_failure(self):
        from bestfgs.error_routing import RoutedTaskRunner
        # Execute production routing against the actual class via a minimal initialized instance.
        r=object.__new__(RoutedTaskRunner);base=active();r.__dict__.update(base.__dict__)
        r._emit=base._emit
        r.local=None;r.routing=SimpleNamespace(reconnaissance=True,local_correction=True)
        r.route_stats=r.counts;r._set_local=lambda *a:setattr(r,'local',dict(remaining=1))
        a=action('cat /proc/net/tcp');r._contrastive_before(a)
        observe(r,a,stdout='NO_SOCKET',return_code=1,stderr='SyntaxError: broken')
        self.assertEqual(r.exploration_results[0]['status'],'unknown')
        self.assertEqual(r.counts['contrastive_failure_records'],2)

if __name__=='__main__':unittest.main()
