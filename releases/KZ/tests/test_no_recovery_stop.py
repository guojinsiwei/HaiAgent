"""Regress the selected KZ base itself, not the newer tools/1234 branch."""
from pathlib import Path
import hashlib,json,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
sys.path.insert(0,str(ROOT))
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_audit import read_trace
from bestfgs.error_routing import RoutedTaskRunner,RoutingPolicy
from bestfgs.rejection_recovery import RejectionRecovery
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment,Scripted,run_action,SUBMIT

class NoRecoveryStopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'evidence/test-temp').mkdir(parents=True,exist_ok=True)
    def exercise(self,*,routed=False,budget=80,advisor_limit=6,submit=True):
        with tempfile.TemporaryDirectory(dir=ROOT/'evidence/test-temp') as temp:
            env=FakeEnvironment();actor=Scripted([run_action('read','f.py')]*40+([SUBMIT] if submit else [run_action('read','f.py')]*60))
            guide=Scripted([dict(alternatives=[])]*10)
            cfg=LeanConfig(max_turns=budget,max_tools=60,contrastive_mode='orthogonal',
                contrastive_predictions=False,memory_reliability=True,outcome_reliability=True,
                memory_decision=False,memory_injection=False,
                diagnostic_advisor_threshold=100,repeated_failure_threshold=100,
                max_advisor_calls=advisor_limit,subgoals_enabled=routed)
            kwargs={}
            cls=LeanTaskRunner
            if routed:
                cls=RoutedTaskRunner
                kwargs=dict(routing=RoutingPolicy(local_correction=True,reconnaissance=True,
                    critic=True,backtracking=True),critic_client=Scripted([
                        dict(decision='accept',requirements=['fixture'],gaps=[],
                            checks=[dict(argv=['check'],stdout_contains=['seed'])]),
                        dict(decision='accept',requirements=['fixture'],gaps=[],checks=[])]))
            runner=cls(env,actor,guide,cfg,Path(temp)/'trace',**kwargs)
            result=runner.run(TaskSpec('no-stop','Inspect public files'))
            events=read_trace(Path(temp)/'trace/events.jsonl')
            self.assertFalse(any(e['event']=='recovery_exhausted' for e in events))
            return result,events
    def test_no_exhaustion_in_controller(self):
        recovery=RejectionRecovery(7)
        for i in range(7):recovery.reject({'f.py':'file:old'})
        self.assertTrue(recovery.advisor_due);recovery.advisor_started()
        for i in range(1000):recovery.reject({'f.py':'file:old'})
        self.assertFalse(recovery.advisor_due)
        self.assertFalse(recovery.view()['hard_stop_enabled'])
        self.assertFalse(hasattr(recovery,'exhausted'))
    def test_actual_runner_can_submit_after_forty_identical_proposals(self):
        result,events=self.exercise()
        self.assertEqual(result['stop_reason'],'model_submit',result)
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['advisor_rounds'],1)
        self.assertGreater(result['mechanism_utilization']['recovery_rejected_turns'],14)
    def test_selected_1342_runner_can_continue_and_deliver(self):
        result,events=self.exercise(routed=True)
        self.assertEqual(result['stop_reason'],'model_submit',result)
        self.assertTrue(result['submitted'])
        self.assertGreater(result['mechanism_utilization']['recovery_rejected_turns'],14)
    def test_original_model_budget_still_stops(self):
        result,events=self.exercise(budget=40,submit=False)
        self.assertEqual(result['stop_reason'],'model_budget',result)
        self.assertEqual(result['interaction_rounds'],40)
    def test_advisor_unavailable_does_not_stop_main(self):
        result,events=self.exercise(advisor_limit=0)
        self.assertEqual(result['stop_reason'],'model_submit',result)
        self.assertEqual(result['advisor_rounds'],0)
    def test_only_two_core_files_change(self):
        lockfile=ROOT/'historic-config-lock.json'
        if not lockfile.exists():
            lockfile=ROOT.parents[1]/'experiment_records/longcli-dh-1342-complete20-20261009/KZ-config-lock.json'
        lock=json.loads(lockfile.read_text())
        changes=[]
        for name,expected in lock['source_hashes'].items():
            if not name.startswith('sources/'):continue
            file=ROOT/name
            if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:changes.append(file.name)
        self.assertEqual(set(changes),{'lean_runtime.py','rejection_recovery.py'})
        self.assertNotIn('recovery_rejection_limit',(ROOT/'sources/bestfgs-project/src/bestfgs/lean_runtime.py').read_text())
    def test_deployment_contract_accepts_only_fixed_source(self):
        from verify_contract import verify
        self.assertFalse(verify(ROOT)['rejection_based_task_stop'])
        original=ROOT.parent/'DH-routing-v1'
        if original.exists():
            with self.assertRaises(AssertionError):verify(original)
        self.assertIn('verify()', (ROOT/'launch.py').read_text())

if __name__=='__main__':
    (ROOT/'evidence/test-temp').mkdir(parents=True,exist_ok=True)
    unittest.main()
