import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
sys.path[:0]=[str(Path(__file__).parent/'legacy/sources/bestfgs-project/src'),str(Path(__file__).parent/'legacy/compatibility/src')]
from bestfgs.exploration_trigger import ExplorationTrigger, check_identity
from bestfgs.contrastive_exploration import ContrastiveExploration

class Runner(ContrastiveExploration):
    def __init__(self):
        self.config=SimpleNamespace(contrastive_mode='orthogonal',contrastive_trigger_failures=2,
            max_memories=24,contrastive_predictions=False,contrastive_episode_tools=8)
        self.counts=Counter();self.events=[];self.saved={}
        self.log=SimpleNamespace(save=lambda k,v:self.saved.update({k:v}))
        self.memory=SimpleNamespace(items={});self.environment=SimpleNamespace()
        self._init_contrastive()
    def _emit(self,event,**fields):self.events.append(dict(event=event,**fields))
    def step(self,eid,command='gcc main.c -o main',code=1,clean=False,before='a',after='a',output='error',complete=True):
        self.counts['tool_calls']+=1
        action=dict(action='run',argv=['bash','-lc',command],cwd='/app')
        row=dict(id=eid,return_code=code,stdout=output,stderr='',before=before,after=after,category='build',
            timed_out=False,blocked=False,capture_incomplete=not complete,terminal_projection_incomplete=False,dependency_after={})
        self._contrastive_outcome(action,row,dict(execution_clean=clean,check_status='unknown'))

class Tests(unittest.TestCase):
    def test_real_runner_unchanged_guard_starts_exploration(self):
        import tempfile
        sys.path.insert(0,str(Path(__file__).parent/'legacy/sources/bestfgs-project/tests'))
        from test_lean import LeanTests, LeanConfig, run_action, SUBMIT
        root=Path(__file__).resolve().parents[3]/'experiment_records/tb2-orthogonal-trigger-audit-20261017/test-tmp'
        root.mkdir(exist_ok=True)
        previous=tempfile.tempdir;tempfile.tempdir=str(root)
        fixture=LeanTests()
        try:
            result,events,_,_,env,runner=fixture.exercise([run_action('fail'),run_action('fail'),SUBMIT],
                config=LeanConfig(max_turns=3,max_tools=10,contrastive_mode='orthogonal',
                                  memory_reliability=True,outcome_reliability=True,memory_decision=False))
            self.assertEqual(len(env.executed),1)
            self.assertEqual(runner.counts['action_loop_blocks'],1)
            starts=[e for e in events if e['event']=='contrastive_episode_start']
            self.assertEqual(len(starts),1)
            self.assertEqual(starts[0]['trigger_evidence']['reason'],'repeated_failure_request')
        finally:
            fixture.doCleanups();tempfile.tempdir=previous
    def test_real_outcome_path_after_edit_and_changed_diagnostic(self):
        r=Runner();r.step('E1');r.step('read','cat main.c',0,True)
        r.step('E3',before='b',after='c',output='different compiler line')
        self.assertEqual(r.counts['contrastive_episodes'],1)
        self.assertEqual(r.events[0]['trigger_evidence']['evidence'],['E1','E3'])
    def test_clean_check_resets_only_itself(self):
        r=Runner();r.step('E1');r.step('E2',code=0,clean=True);r.step('E3')
        self.assertEqual(r.counts['contrastive_episodes'],0)
    def test_unrelated_checks_not_pooled(self):
        r=Runner();r.step('E1');r.step('E2','gcc other.c -o main');self.assertIsNone(r.contrastive_episode)
    def test_uncertain_and_incomplete_do_not_fake_failure_or_success(self):
        r=Runner();r.step('E1');r.step('E2',code=0,clean=False);r.step('E3',complete=False)
        self.assertIsNone(r.contrastive_episode);r.step('E4');self.assertIsNotNone(r.contrastive_episode)
    def test_duplicate_block_receipt_cannot_rearm(self):
        r=Runner();r.step('E1');key=check_identity('gcc main.c -o main','/app')
        r.exploration_trigger.blocked(key,'E1');r._contrastive_activate('unchanged_action_loop')
        self.assertEqual(r.counts['contrastive_episodes'],1)
        r.contrastive_episode=None;r.exploration_trigger.retire_pending()
        for _ in range(20):
            r.exploration_trigger.blocked(key,'E1');r._contrastive_activate('unchanged_action_loop')
        self.assertEqual(r.counts['contrastive_episodes'],1)
    def test_auxiliary_tools_leave_probe_window_open(self):
        r=Runner();r.step('E1');r.step('E2')
        for i in range(8):r.step('during'+str(i))
        self.assertIsNotNone(r.contrastive_episode)
        self.assertEqual(r.contrastive_episode['probes'],0)
    def test_disabled(self):
        r=Runner();r.config.contrastive_mode='off';r.step('E1');r.step('E2');self.assertIsNone(r.contrastive_episode)
    def test_family_identity(self):
        self.assertEqual(check_identity('cd /app && gcc -Wall main.c -o a; echo done'),check_identity('gcc main.c -o b','/app'))
        self.assertEqual(check_identity('(sleep 8) | timeout 25 telnet 127.0.0.1 6665 | grep login'),check_identity('timeout 15 telnet 127.0.0.1 6665 | head'))
        self.assertNotEqual(check_identity('telnet 127.0.0.1 6665'),check_identity('telnet 127.0.0.1 7777'))
    def test_restore_and_deduplicate(self):
        t=ExplorationTrigger();t.observe('x','E1','failed');q=ExplorationTrigger(t.state)
        q.observe('x','E1','failed');self.assertIsNone(q.pending(2));q.observe('x','E2','failed');self.assertIsNotNone(q.pending(2))

if __name__=='__main__':unittest.main()
