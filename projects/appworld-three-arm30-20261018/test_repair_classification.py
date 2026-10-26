import tempfile,unittest,json
from pathlib import Path
from repair_classification import classify,retry_eligible
class RepairClassification(unittest.TestCase):
    def test_legacy_stop_is_corrected_and_only_failed_affected_trials_retry(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);(d/'audit').mkdir();(d/'audit/dsh.stderr.log').write_text('KZ per-task monetary ceiling; next request not sent, artifacts retained')
            s={'engineering_fault':'solver_process_error','official_success':True,'grading':'complete'}
            r=classify(s,d);self.assertNotIn('engineering_fault',r);self.assertFalse(retry_eligible(r));self.assertTrue(r['official_success'])
            s['official_success']=False;self.assertTrue(retry_eligible(classify(s,d)))
            (d/'repair-version.json').write_text('{}');self.assertFalse(retry_eligible(classify(s,d)))
    def test_rpc_failure_is_not_provider_failure_or_wall_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            r=classify({'budget_reason':'budget_service_unavailable','engineering_fault':'provider_transport_or_http','stop_reason':'wall_budget','official_success':False},t)
            self.assertEqual(r['stop_reason'],'budget_service_unavailable');self.assertTrue(retry_eligible(r))
if __name__=='__main__':unittest.main()
