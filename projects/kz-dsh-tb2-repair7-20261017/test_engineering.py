import copy
import json
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import campaign
import experiment
from recovery import reconcile, owned_alive
from receipts import lifecycle_status
from storage import atomic_json
from trial_runner import run


def lifecycle(attempt='abc'):
    return dict(schema_version=2,attempt_id=attempt,failures=[],stage='cleanup_succeeded',
                events=[dict(stage=s) for s in ('collecting','artifacts_collected','verifying',
                       'verifier_finished','cleanup_started','cleanup_succeeded')])


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patch=patch.object(campaign,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.trial=self.root/'jobs/j/t';self.live=self.trial/'agent/live';self.live.mkdir(parents=True)
        atomic_json(self.trial/'result.json',dict(verifier_result=dict(rewards=dict(reward=0))))
        atomic_json(self.live/'agent-exit.json',dict(attempt_id='abc',exit_code=0,timed_out=False))
        self.row=dict(job='j',attempt_id='abc')

    def test_missing_corrupt_unfinished_wrong_identity_cannot_be_clean(self):
        cases=[None,'{',[],{},dict(lifecycle(),stage='collecting'),lifecycle('old')]
        for value in cases:
            with self.subTest(value=value):
                path=self.trial/'lifecycle.json'
                path.unlink(missing_ok=True)
                if isinstance(value,str):path.write_text(value)
                elif value is not None:atomic_json(path,value)
                self.assertFalse(campaign.trial(self.row)['engineering_clean'])

    def test_valid_zero_score_is_clean(self):
        atomic_json(self.trial/'lifecycle.json',lifecycle())
        self.assertTrue(campaign.trial(self.row)['engineering_clean'])

    def test_unknown_usage_is_engineering_failure_not_model_score(self):
        atomic_json(self.trial/'lifecycle.json',lifecycle())
        atomic_json(self.live/'budget-stop.json',dict(reason='usage_unavailable'))
        result=campaign.trial(self.row)
        self.assertFalse(result['engineering_clean'])
        self.assertEqual(result['reward'],0)

    def test_budget_cannot_override_missing_lifecycle(self):
        atomic_json(self.live/'agent-exit.json',dict(attempt_id='abc',exit_code=143,timed_out=True))
        atomic_json(self.live/'wall-limit.json',dict(attempt_id='abc',state='enforced',reason='solver_wall_limit',limit_seconds=2700))
        result=campaign.trial(self.row)
        self.assertTrue(result['budget_exhausted']);self.assertFalse(result['engineering_clean'])

    def test_old_exit_receipt_does_not_belong_to_new_attempt(self):
        atomic_json(self.trial/'lifecycle.json',lifecycle())
        atomic_json(self.live/'agent-exit.json',dict(attempt_id='old',exit_code=0,timed_out=False))
        self.assertFalse(campaign.trial(self.row)['engineering_clean'])

    def test_malformed_route_preserves_known_cost_and_marks_incomplete(self):
        atomic_json(self.trial/'lifecycle.json',lifecycle())
        (self.live/'route.jsonl').write_text('{"event":"request_shape"}\n{')
        result=campaign.trial(self.row)
        self.assertEqual(result['actual_http_attempts'],1)
        self.assertEqual(result['malformed_route_records'],1)
        self.assertFalse(result['engineering_clean'])

    def test_completed_stage_without_ordered_receipts_is_incomplete(self):
        receipt=lifecycle();receipt['events'].reverse()
        atomic_json(self.trial/'lifecycle.json',receipt)
        self.assertEqual(lifecycle_status(self.trial/'lifecycle.json','abc')[0],'incomplete')


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.state=dict(rows=[dict(job='j',state='running',attempt_id='abc',stage='first')],phase='first',active=[])
        self.receipt=dict(schema_version=1,attempt_id='abc',state='completed',harbor_exit=0,runner={'pid':1},harbor={'pid':2})

    def recover(self,alive=lambda _:False):
        return reconcile(self.root,self.state,lambda *a:dict(engineering_clean=True,reward=0),alive)

    def test_missing_admission_receipt_blocks_without_mutation(self):
        original=copy.deepcopy(self.state)
        state,problems=self.recover()
        self.assertIsNone(state);self.assertTrue(problems);self.assertEqual(self.state,original)

    def test_finished_attempt_is_reconciled_without_relaunch(self):
        atomic_json(self.root/'attempts/abc.json',self.receipt)
        state,problems=self.recover()
        self.assertFalse(problems);self.assertEqual(state['rows'][0]['state'],'done')

    def test_live_runner_or_harbor_blocks_resume(self):
        atomic_json(self.root/'attempts/abc.json',self.receipt)
        for pid in (1,2):
            _,problems=self.recover(lambda x:bool(x and x.get('pid')==pid))
            self.assertTrue(problems)

    def test_harbor_nonzero_never_becomes_clean(self):
        atomic_json(self.root/'attempts/abc.json',{**self.receipt,'harbor_exit':1})
        state,_=self.recover()
        self.assertEqual(state['rows'][0]['state'],'engineering_failure')

    def test_resume_preserves_prior_trials_and_pending_queue(self):
        self.state['rows']=[dict(job='done',state='done',result={'requests':23}),dict(job='next',state='pending')]
        state,problems=self.recover()
        self.assertFalse(problems);self.assertEqual(state['rows'],self.state['rows'])

    def test_pid_reuse_is_not_owned(self):
        with patch('recovery.process_identity',return_value={'pid':9,'start':'new','boot':'same'}):
            self.assertFalse(owned_alive({'pid':9,'start':'old','boot':'same'}))

    def test_real_child_exit_is_recorded_without_any_model_or_harbor(self):
        self.assertEqual(run([sys.executable,'-c','raise SystemExit(7)'],self.root,'abc'),7)
        receipt=json.loads((self.root/'attempts/abc.json').read_text())
        self.assertEqual(receipt['schema_version'],1)
        self.assertEqual(receipt['state'],'completed')
        self.assertEqual(receipt['harbor_exit'],7)

    def test_wrapper_persists_exit_and_never_reuses_attempt(self):
        class Child:
            pid=123
            def wait(self):return 7
        with patch('trial_runner.process_identity',return_value=None):
            self.assertEqual(run(['fixture'],self.root,'abc',popen=lambda *a,**k:Child()),7)
            result=json.loads((self.root/'attempts/abc.json').read_text())
            self.assertEqual(result['harbor_exit'],7);self.assertEqual(result['state'],'completed')
            with self.assertRaisesRegex(RuntimeError,'already'):
                run(['fixture'],self.root,'abc',popen=lambda *a,**k:self.fail('relaunch'))


class ProtocolTests(unittest.TestCase):
    def test_generated_protocol_has_no_legacy_retry_contradictions(self):
        config=experiment.load(Path(__file__).parent)
        fields=experiment.protocol_fields(config)
        self.assertTrue(fields['no_automatic_paid_retries'])
        self.assertEqual(fields['paid_attempts_per_arm_task'],1)
        self.assertEqual(fields['max_trials_with_retry'],7)

    def test_stale_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=experiment.load(Path(__file__).parent)
            atomic_json(root/'experiment.json',config)
            atomic_json(root/'protocol.json',dict(experiment.protocol_fields(config),no_automatic_paid_retries=False))
            with self.assertRaisesRegex(ValueError,'no_automatic_paid_retries'):
                experiment.validate_protocol(root)


if __name__=='__main__':unittest.main()
