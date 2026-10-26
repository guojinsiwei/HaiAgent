"""Real disposable local files and scripted policies; no model/network calls."""
from copy import deepcopy
import ast
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec
from bestfgs.route_selection import parse_experiment, check_result
from test_lean import Scripted, SUBMIT, run_action


def py(code):
    return dict(argv=['python3', '-c', code])


def plan(a='bad', b='good', probe='unknown'):
    return dict(probe=py('print('+repr(probe)+')'),
        check=py("from pathlib import Path; import sys; p=Path('result.txt'); ok=p.exists() and p.read_text().startswith('good'); print('CHECK_PASS' if ok else 'CHECK_FAIL'); sys.exit(0 if ok else 1)"),
        pass_contains='CHECK_PASS', fail_contains='CHECK_FAIL', routes=[
            dict(hypothesis='The first construction method is needed', supports='CAUSE_A', refutes='CAUSE_B',
                 targets=['result.txt'], steps=[py("from pathlib import Path; Path('result.txt').write_text("+repr(a)+")")]),
            dict(hypothesis='The alternative construction method is needed', supports='CAUSE_B', refutes='CAUSE_A',
                 targets=['result.txt'], steps=[py("from pathlib import Path; Path('result.txt').write_text("+repr(b)+")")])])


class RouteTests(unittest.TestCase):
    def exercise(self, proposal=None, config=None, extra_files=None, actions=None, env_class=LiveWorkspace):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); seed = root/'seed'; seed.mkdir()
        (seed/'seed.txt').write_text('unchanged fixture')
        for name, value in (extra_files or {}).items():
            (seed/name).write_text(value)
        env = env_class(seed, root/'state')
        read = run_action('cat','seed.txt')
        actions = actions or [read]*3+[dict(read, route_experiment=proposal or plan()), SUBMIT]
        actor = Scripted(actions)
        cfg = config or LeanConfig(max_tools=30, max_turns=20, wall_seconds=500, max_advisor_calls=0,
            memory_reliability=True, outcome_reliability=True, stagnation_control=True, route_search=True)
        runner = LeanTaskRunner(env, actor, Scripted([]), cfg, root/'audit')
        result = runner.run(TaskSpec('route-fixture','Create result.txt beginning with good'))
        self.assertIsNone(result['error_type'], result)
        return runner, result, env, read_trace(root/'audit/events.jsonl'), actor

    def test_unknown_probe_trials_both_and_selects_actual_improvement(self):
        r,out,env,events,actor = self.exercise()
        self.assertEqual((env.workspace/'result.txt').read_text(),'good')
        self.assertEqual(r.route_episode['selected'],'B')
        self.assertEqual(r.counts['route_trials'],2)
        self.assertEqual(r.counts['route_tools'],6)
        self.assertEqual(out['tool_calls'],9)
        self.assertEqual(out['interaction_rounds'],5)
        self.assertEqual([x['verdict'] for x in r.route_episode['results']],['fail','pass'])
        starts=[e['scope'] for e in events if e['event']=='route_trial_started']
        self.assertEqual(starts,[r.route_episode['condition_scope']]*2)
        self.assertEqual(r.route_memory[0]['status'],'failed_public_check')
        self.assertIsNone(r.route_memory[1]['task_success'])
        self.assertEqual(len(actor.prompts),5)

    def test_probe_refutes_a_and_allocates_tools_only_to_b(self):
        r,out,env,events,_=self.exercise(plan(probe='CAUSE_B'))
        self.assertEqual(r.counts['route_pruned'],1)
        self.assertEqual(r.counts['route_trials'],1)
        self.assertEqual(r.counts['route_tools'],4)
        self.assertEqual(r.route_episode['selected'],'B')
        self.assertEqual(r.route_memory[0]['status'],'prediction_refuted')

    def test_conflicting_predictions_do_not_prune(self):
        r,*_=self.exercise(plan(probe='CAUSE_A CAUSE_B'))
        self.assertEqual(r.route_episode['predictions'],{'A':'unknown','B':'unknown'})
        self.assertEqual(r.counts['route_trials'],2)

    def test_failed_probe_is_unknown_not_refutation(self):
        p=plan();p['probe']=py("print('CAUSE_B'); raise RuntimeError('probe itself failed')")
        r,*_=self.exercise(p)
        self.assertEqual(r.counts['route_pruned'],0)
        self.assertEqual(r.counts['route_trials'],2)

    def test_both_fail_restore_base_and_record_conditional_failures(self):
        r,out,env,events,_=self.exercise(plan('bad A','bad B'))
        self.assertFalse((env.workspace/'result.txt').exists())
        self.assertEqual(r.route_episode['finish_reason'],'no_candidate_improved')
        self.assertEqual(r.counts['route_selected'],0)
        self.assertTrue(all(m['status']=='failed_public_check' for m in r.route_memory))
        self.assertEqual(env.scope(),r.route_episode['condition_scope'])

    def test_second_candidate_does_not_inherit_first_candidates_files(self):
        p=plan()
        p['routes'][0]['steps']=[py("from pathlib import Path; Path('first.txt').write_text('scratch'); Path('result.txt').write_text('bad')")]
        p['routes'][1]['steps']=[py("from pathlib import Path; assert not Path('first.txt').exists(); Path('result.txt').write_text('good')")]
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.route_episode['selected'],'B')
        self.assertFalse((env.workspace/'first.txt').exists())

    def test_equal_checks_choose_cheaper_candidate_not_later_candidate(self):
        p=plan('good A','good B')
        p['routes'][1]['steps'].insert(0,py("print('preparing B')"))
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.route_episode['selected'],'A')
        self.assertEqual((env.workspace/'result.txt').read_text(),'good A')
        self.assertEqual(len(r.route_episode['results']),2)

    def test_baseline_already_passes_does_not_modify_files(self):
        r,out,env,*_=self.exercise(extra_files={'result.txt':'good original'})
        self.assertEqual(r.counts['route_tools'],1)
        self.assertEqual(r.counts['route_trials'],0)
        self.assertEqual((env.workspace/'result.txt').read_text(),'good original')
        self.assertEqual(r.route_episode['finish_reason'],'baseline_already_passes')

    def test_absent_failure_marker_is_inconclusive(self):
        p=plan();p['check']=py("print('test harness crashed'); raise SystemExit(2)")
        r,*_=self.exercise(p)
        self.assertEqual(r.counts['route_trials'],0)
        self.assertEqual(r.route_episode['finish_reason'],'baseline_inconclusive')

    def test_probe_modification_is_rolled_back(self):
        p=plan();p['probe']=py("from pathlib import Path; Path('dirty.txt').write_text('oops'); print('CAUSE_B')")
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.counts['route_trials'],0)
        self.assertFalse((env.workspace/'dirty.txt').exists())
        self.assertEqual(r.route_episode['finish_reason'],'probe_mutated_workspace')

    def test_check_modification_is_not_a_pass(self):
        p=plan();p['check']=py("from pathlib import Path; Path('dirty.txt').write_text('oops'); print('CHECK_PASS')")
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.counts['route_selected'],0)
        self.assertFalse((env.workspace/'dirty.txt').exists())

    def test_failure_cannot_become_pass_by_actor_self_report(self):
        p=plan('bad A','bad B');p['verified']=True;p['selected']='B'
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.counts['route_selected'],0)
        self.assertFalse((env.workspace/'result.txt').exists())

    def test_missing_proposal_gates_only_twice(self):
        read=run_action('cat','seed.txt')
        r,out,env,events,_=self.exercise(actions=[read]*7+[SUBMIT])
        self.assertEqual(r.counts['route_plans'],0)
        self.assertEqual(r.route_episode['finish_reason'],'no_valid_experiment_proposed')
        self.assertTrue(out['submitted'])
        self.assertEqual(sum(e['event']=='conversation_turn' and e['feedback'].get('not_executed',False) for e in events),2)

    def test_no_new_budget_if_remaining_tools_are_insufficient(self):
        cfg=LeanConfig(max_tools=10,max_turns=20,wall_seconds=500,max_advisor_calls=0,
                       outcome_reliability=True,stagnation_control=True,route_search=True)
        read=run_action('cat','seed.txt')
        r,out,*_=self.exercise(config=cfg,actions=[read]*3+[SUBMIT])
        self.assertEqual(r.counts['route_episodes'],0)
        self.assertEqual(out['tool_calls'],3)

    def test_no_new_budget_if_remaining_time_is_insufficient(self):
        cfg=LeanConfig(max_tools=30,max_turns=20,wall_seconds=90,max_advisor_calls=0,
                       outcome_reliability=True,stagnation_control=True,route_search=True)
        read=run_action('cat','seed.txt')
        r,out,*_=self.exercise(config=cfg,actions=[read]*3+[SUBMIT])
        self.assertEqual(r.counts['route_episodes'],0)

    def test_model_budget_exit_closes_admitted_experiment(self):
        cfg=LeanConfig(max_tools=30,max_turns=4,wall_seconds=500,max_advisor_calls=0,
                       outcome_reliability=True,stagnation_control=True,route_search=True)
        r,out,env,*_=self.exercise(config=cfg)
        self.assertEqual(r.route_episode['status'],'closed')
        self.assertEqual(r.counts['route_tools'],0)
        self.assertEqual(env.scope(),r.route_episode['condition_scope'])

    def test_abort_during_trial_restores_files(self):
        class Ending(LeanTaskRunner):
            def _route_execute(self, cmd, role):
                row=super()._route_execute(cmd,role)
                if role=='trial_A':self.route_episode['expires']=time.monotonic()-1
                return row
        with patch(f'{__name__}.LeanTaskRunner',Ending):
            r,out,env,*_=self.exercise()
        self.assertFalse((env.workspace/'result.txt').exists())
        self.assertEqual(r.route_episode['finish_reason'],'experiment_budget_exhausted')

    def test_repeated_failed_route_is_pruned_by_same_condition_memory(self):
        read=run_action('cat','seed.txt');p=plan('bad A','bad B')
        actions=[read]*3+[dict(read,route_experiment=p)]+[read]*12+[dict(read,route_experiment=deepcopy(p)),SUBMIT]
        r,out,env,*_=self.exercise(actions=actions,config=LeanConfig(max_tools=60,max_turns=30,wall_seconds=500,
            max_advisor_calls=0,outcome_reliability=True,stagnation_control=True,route_search=True))
        self.assertEqual(r.counts['route_plans'],2)
        self.assertEqual(r.counts['route_trials'],2)
        self.assertEqual(r.counts['route_pruned'],2)
        self.assertTrue(all(x=='previous_failure_same_condition' for x in r.route_episode['predictions'].values()))

    def test_budget_abort_preserves_already_verified_candidate(self):
        class Ending(LeanTaskRunner):
            def _route_execute(self, cmd, role):
                row=super()._route_execute(cmd,role)
                if role=='trial_B':self.route_episode['expires']=time.monotonic()-1
                return row
        with patch(f'{__name__}.LeanTaskRunner',Ending):
            r,out,env,*_=self.exercise(plan('good A','bad B'))
        self.assertEqual(r.route_episode['selected'],'A')
        self.assertEqual((env.workspace/'result.txt').read_text(),'good A')

    def test_new_probe_observation_reopens_previously_failed_route(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        external=Path(tmp.name)/'external.txt';external.write_text('unknown')
        p=plan('bad A','bad B');p['probe']=py('from pathlib import Path; print(Path('+repr(str(external))+').read_text())')
        class Changing(LeanTaskRunner):
            def _route_finish(self, reason, winner=None):
                super()._route_finish(reason,winner)
                if self.route_episode['id']=='S1':external.write_text('CAUSE_A')
        read=run_action('cat','seed.txt')
        actions=[read]*3+[dict(read,route_experiment=p)]+[read]*12+[dict(read,route_experiment=deepcopy(p)),SUBMIT]
        with patch(f'{__name__}.LeanTaskRunner',Changing):
            r,out,env,*_=self.exercise(actions=actions,config=LeanConfig(max_tools=60,max_turns=30,wall_seconds=500,
                max_advisor_calls=0,outcome_reliability=True,stagnation_control=True,route_search=True))
        self.assertEqual(r.counts['route_trials'],3)
        self.assertEqual(r.route_episode['predictions']['A'],'supported')

    def test_passing_check_without_target_change_does_not_select_route(self):
        p=plan()
        p['check']=py("from pathlib import Path; import sys; ok=Path('unrelated.txt').exists(); print('CHECK_PASS' if ok else 'CHECK_FAIL'); sys.exit(0 if ok else 1)")
        for i,r in enumerate(p['routes']):
            r['steps']=[py("from pathlib import Path; Path('unrelated.txt').write_text("+repr(str(i))+")")]
        r,out,env,*_=self.exercise(p)
        self.assertEqual(r.counts['route_selected'],0)
        self.assertTrue(all(x['verdict']=='pass' and not x['changed_targets'] for x in r.route_episode['results']))
        self.assertFalse((env.workspace/'unrelated.txt').exists())


class ProtocolTests(unittest.TestCase):
    def test_adapter_release_label_is_not_inherited_v5(self):
        tree=ast.parse((ROOT/'integration/transport.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TripleAgent')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='version')
        self.assertEqual(ast.literal_eval(method.body[0].value),'route-selection-v7')

    def test_duplicate_hypothesis_rejected(self):
        p=plan();p['routes'][1]['hypothesis']=p['routes'][0]['hypothesis']
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_renaming_same_commands_is_not_a_competing_route(self):
        p=plan();p['routes'][1]['steps']=deepcopy(p['routes'][0]['steps'])
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_unsafe_target_rejected(self):
        p=plan();p['routes'][0]['targets']=['../outside']
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_overlapping_prediction_rejected(self):
        p=plan();p['routes'][0]['refutes']='CAUSE_A suffix'
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_blind_echo_is_not_a_check(self):
        p=plan();p['check']={'argv':['echo','CHECK_PASS']}
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_excessive_step_count_rejected(self):
        p=plan();p['routes'][0]['steps']*=4
        with self.assertRaises(ValueError):parse_experiment(p)

    def test_timeout_capped_without_changing_total_budget(self):
        p=plan();p['probe']['timeout_seconds']=900
        self.assertEqual(parse_experiment(p)['probe']['timeout_seconds'],15)

    def test_conflicting_check_markers_unknown(self):
        row=dict(stdout='CHECK_PASS CHECK_FAIL',stderr='',capture_incomplete=False,timed_out=False,
                 blocked=False,before='x',after='x',execution_assessment={'execution_clean':True})
        self.assertEqual(check_result(row,plan()),'unknown')

    def test_truncated_check_does_not_pass(self):
        row=dict(stdout='CHECK_PASS',stderr='',capture_incomplete=True,timed_out=False,
                 blocked=False,before='x',after='x',execution_assessment={'execution_clean':True})
        self.assertEqual(check_result(row,plan()),'unknown')

    def test_direct_config_requires_reliability_prerequisites(self):
        with self.assertRaises(ValueError):LeanConfig(route_search=True)


if __name__=='__main__':unittest.main()
