import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from collections import Counter, OrderedDict

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_audit import read_trace
from bestfgs.lean_monitor import SemanticHooks,MONITOR_SYSTEM
from bestfgs.monitor_context import schedule,build_context
from bestfgs.models import TaskSpec,CommandSpec,CommandResult
from bestfgs.tool_outcomes import assess
from test_lean import FakeEnvironment,Scripted,SUBMIT,run_action


class ContextTests(unittest.TestCase):
    def dummy(self, goal='long task '*3000):
        row=dict(id='E1',argv='read',purpose='inspect',stdout='x'*5000,stderr='',before='s',after='s',return_code=0)
        return SimpleNamespace(task=SimpleNamespace(goal=goal,constraints=['Respect task boundaries']),
            config=LeanConfig(monitor_reliability=True),evidence=OrderedDict((f'E{i}',dict(row,id=f'E{i}')) for i in range(1,49)),
            memory_pending={},memory=SimpleNamespace(items={}),monitor_review={},
            progress=SimpleNamespace(view=lambda:dict(criteria=[dict(criterion=goal)],missing_artifacts=['outputs/a.json'],requested_artifacts=[])),
            environment=SimpleNamespace(scope=lambda:'s'))

    def test_long_task_does_not_eliminate_evidence(self):
        r=self.dummy();p,d=build_context(r,'periodic_review',17059)
        self.assertLessEqual(d['chars'],17059);self.assertGreaterEqual(len(p['evidence']),8)
        self.assertTrue(p['task']['partial']);self.assertNotIn('criteria',p['delivery'])

    def test_unicode_quotes_newlines_still_fit(self):
        p,d=build_context(self.dummy('中文"\\\n'*12000),'periodic_review',17059)
        self.assertLessEqual(len(json.dumps(p,ensure_ascii=False)),17059)
        self.assertEqual(len(p['task']['goal_sha256']),64)

    def test_minimal_mode_is_explicit(self):
        p,d=build_context(self.dummy(),'periodic_review',7000)
        self.assertEqual(d['mode'],'minimal');self.assertTrue(all(e['monitor_view_partial'] for e in p['evidence']))

    def test_long_intervention_does_not_break_small_context(self):
        r=self.dummy();r.control_view=lambda:dict(reason='r'*700,plan={'action':'x'*5000},status='planned')
        p,d=build_context(r,'recovery_failed',5059)
        self.assertLessEqual(d['chars'],5059);self.assertGreaterEqual(d['evidence_count'],2)

    def test_budget_reserved_for_end_of_run(self):
        r=self.dummy('task');r.config=LeanConfig(monitor_reliability=True)
        r.started_at=time.monotonic();r.monitor_lanes=Counter();r.monitor_event='failure_cluster';r.counts=Counter()
        calls=[];last=0
        for n in range(8,600):
            r.counts['tool_calls']=n
            if n-last<8:continue
            value=schedule(r)
            if value:
                lane,why=value;r.monitor_lanes[lane]+=1;calls.append(n);last=n
        self.assertLessEqual(len(calls),12);self.assertGreaterEqual(calls[-1],550)
        self.assertEqual(r.monitor_lanes['periodic'],6)

    def test_bad_memory_does_not_discard_valid_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            mon=Scripted([dict(verdict='progress',reason='Useful evidence',evidence_ids=['E1','E2'],memories='invalid')])
            cfg=LeanConfig(max_tools=8,max_turns=12,semantic_monitor=True,auto_memory=True,monitor_reliability=True,
                           monitor_cooldown_tools=2,monitor_interval_tools=3,max_monitor_calls=3)
            r=LeanTaskRunner(FakeEnvironment(),Scripted([run_action('read','A'),run_action('read','B'),SUBMIT]),
                            Scripted([]),cfg,Path(tmp)/'audit',monitor_client=mon)
            out=r.run(TaskSpec('t','produce result'))
            self.assertIsNone(out['error_type']);self.assertEqual(r.counts['monitor_reviews_accepted'],1)
            self.assertEqual(r.counts['auto_memories_rejected'],1)


class ExecutionTests(unittest.TestCase):
    def execute(self, code, timeout=5):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);seed=root/'seed';seed.mkdir()
        env=LiveWorkspace(seed,root/'run');env.outcome_reliability=True
        return env.execute(dict(argv=['bash','-lc',code],timeout_seconds=timeout),time.monotonic()+10)

    def test_pipeline_stage_failure_preserved_without_changing_exit(self):
        r=self.execute("python3 -c 'raise RuntimeError(\"broken\")' 2>&1 | tail -5")
        self.assertEqual(r.return_code,0)
        self.assertIn([1,0],r.execution_observation['pipelines'])
        self.assertTrue(assess(r)['suspected_failure']);self.assertFalse(assess(r)['execution_clean'])
        self.assertEqual(assess(r)['check_status'],'unknown')

    def test_debug_trap_override_is_not_clean(self):
        r=self.execute("trap ':' DEBUG; false | true; echo done")
        self.assertEqual(r.return_code,0)
        self.assertFalse(r.execution_observation['complete'])
        self.assertFalse(assess(r)['execution_clean'])

    def test_multiple_pipelines_and_later_success(self):
        r=self.execute('false | cat; printf hello | cat; echo done')
        self.assertEqual(r.stdout,'hellodone\n');self.assertEqual(r.return_code,0)
        self.assertIn([1,0],r.execution_observation['pipelines']);self.assertIn([0,0],r.execution_observation['pipelines'])

    def test_handled_failure_is_warning_not_hard_failure(self):
        r=self.execute('false || echo recovered')
        a=assess(r);self.assertTrue(a['process_succeeded']);self.assertFalse(a['failure_observed'])
        self.assertTrue(a['suspected_failure']);self.assertIsNone(a['task_success'])

    def test_explicit_exit_status_preserved(self):
        r=self.execute('echo before; exit 7');self.assertEqual(r.return_code,7)

    def test_errexit_pipefail_and_status_expansion_unchanged(self):
        r=self.execute('set -e -o pipefail; false | cat; echo unreachable')
        self.assertNotEqual(r.return_code,0);self.assertNotIn('unreachable',r.stdout)
        r=self.execute('false; echo status=$?; printf "%s" "$0"',5)
        self.assertIn('status=1',r.stdout)

    def test_task_trap_override_not_claimed_complete(self):
        r=self.execute("trap 'echo custom' EXIT; echo done")
        self.assertFalse(r.execution_observation['complete']);self.assertIn('custom',r.stdout)
        self.assertFalse(assess(r)['execution_clean'])

    def test_exec_escape_is_partial_coverage(self):
        r=self.execute('exec echo final')
        self.assertEqual(r.return_code,0);self.assertFalse(r.execution_observation['complete'])

    def test_timeout_is_not_success(self):
        r=self.execute('sleep 3',1)
        self.assertTrue(r.timed_out);self.assertFalse(assess(r)['execution_clean'])

    def test_long_shell_trace_is_bounded_and_marked_partial(self):
        r=self.execute('; '.join(['true']*160))
        self.assertTrue(r.execution_observation['trace_truncated'])
        self.assertFalse(r.execution_observation['complete'])

    def test_echo_traceback_word_not_failure(self):
        r=self.execute("echo 'Documentation: Traceback examples'")
        self.assertFalse(assess(r)['suspected_failure'])

    def test_zero_exit_read_not_check_success(self):
        r=self.execute('echo contents');self.assertEqual(assess(r)['check_status'],'unknown')
        r=self.execute("echo '=== 3 passed in 0.1s ==='")
        self.assertEqual(assess(r)['check_status'],'unknown')

    def test_public_check_requires_clear_summary(self):
        r=CommandResult(CommandSpec(('pytest',),'test'),0,'=== 3 passed in 0.1s ===','',0)
        self.assertEqual(assess(r)['check_status'],'public_check_passed')
        self.assertEqual(assess(CommandResult(r.command,0,r.stdout,'',0,output_truncated=True))['check_status'],'unknown')

    def test_uninstrumented_shell_is_unknown_not_clean(self):
        r=CommandResult(CommandSpec(('sh','-c','false | cat'),'pipeline'),0,'','',0)
        self.assertFalse(assess(r)['execution_clean'])
        self.assertFalse(assess(r)['failure_observed'])


class RecoveryTests(unittest.TestCase):
    def exercise(self, actions, env=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        cfg=LeanConfig(max_turns=60,max_tools=45,max_advisor_calls=0,memory_reliability=True,
                       outcome_reliability=True,stagnation_control=True)
        actor=Scripted(actions)
        runner=LeanTaskRunner(env or FakeEnvironment(),actor,Scripted([]),cfg,Path(tmp.name)/'audit')
        result=runner.run(TaskSpec('fixture','Create outputs/result.txt'))
        self.assertIsNone(result['error_type'],result)
        return runner,read_trace(Path(tmp.name)/'audit/events.jsonl'),actor

    def plan(self, **extra):
        return dict(hypothesis='Missing required artifact',mode='repair',targets=['out.txt'],
                    action_argv=['artifact','out.txt','ok'],verification_argv=['read'],success_contains='out.txt:ok',**extra)

    def test_repeated_read_repair_and_separate_verification(self):
        r,e,a=self.exercise([run_action('read')]*3+[
            run_action('artifact','out.txt','ok',recovery_plan=self.plan()),run_action('read'),SUBMIT])
        self.assertEqual(r.counts['recovery_verified_repairs'],1)
        self.assertEqual(r.recovery['status'],'verified_public_check')
        self.assertIsNone(next(x for x in reversed(e) if x['event']=='recovery_followup')['task_success'])

    def test_self_report_without_execution_does_not_verify(self):
        r,e,a=self.exercise([run_action('read')]*3+[
            run_action('read',recovery_plan=self.plan()),run_action('read'),SUBMIT])
        self.assertEqual(r.counts['recovery_verified_repairs'],0)

    def test_warning_output_does_not_pass_verification(self):
        class Bad(FakeEnvironment):
            def execute(self,action,deadline):
                r=super().execute(action,deadline)
                if action['argv'][0]=='check':
                    from dataclasses import replace
                    return replace(r,stdout='Traceback (most recent call last):\nRuntimeError: bad\nok')
                return r
        p=self.plan();p['verification_argv']=['check'];p['success_contains']='ok'
        r,e,a=self.exercise([run_action('read')]*3+[run_action('artifact','out.txt','ok',recovery_plan=p),run_action('check'),SUBMIT],Bad())
        self.assertEqual(r.counts['recovery_verified_repairs'],0);self.assertEqual(r.counts['recovery_failed'],1)

    def test_ignored_plan_expires_and_reopens_route_selection(self):
        r,e,a=self.exercise([run_action('read')]*3+[run_action('read',recovery_plan=self.plan())]+[run_action('read')]*12+[SUBMIT])
        self.assertGreaterEqual(r.counts['recovery_failed'],1)
        self.assertTrue(any(x['event']=='recovery_failed' and 'eight_tools' in x['reason'] for x in e))

    def test_missing_plan_gate_is_bounded(self):
        r,e,a=self.exercise([run_action('read')]*9+[SUBMIT])
        self.assertTrue(any(x['event']=='conversation_turn' and x['feedback'].get('not_executed') for x in e))
        self.assertGreaterEqual(r.counts['tool_calls'],5)

    def test_same_failed_plan_rejected_until_state_changes(self):
        bad=self.plan();bad['success_contains']='absent'
        actions=[run_action('read')]*3+[run_action('artifact','out.txt','ok',recovery_plan=bad),
            run_action('read'),run_action('read',recovery_plan=bad),SUBMIT]
        r,e,a=self.exercise(actions)
        self.assertTrue(any(x['event']=='recovery_plan_rejected' and 'unchanged workspace' in x['reason'] for x in e))

    def test_real_change_not_just_different_command_is_required(self):
        p=self.plan();p['action_argv']=['read','alternative'];p['success_contains']='seed'
        r,e,a=self.exercise([run_action('read')]*3+[run_action('read','alternative',recovery_plan=p),run_action('read'),SUBMIT])
        self.assertEqual(r.counts['recovery_verified_repairs'],0)
        self.assertEqual(r.counts['recovery_failed'],1)

    def test_unsafe_target_does_not_enter_plan(self):
        p=self.plan();p['targets']=['../outside']
        r,e,a=self.exercise([run_action('read')]*3+[run_action('read',recovery_plan=p),SUBMIT])
        self.assertEqual(r.counts['recovery_plans'],0)
        self.assertTrue(any(x['event']=='recovery_plan_rejected' for x in e))

if __name__=='__main__':unittest.main()
