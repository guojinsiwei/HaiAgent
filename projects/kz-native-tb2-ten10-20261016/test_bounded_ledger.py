import tempfile,unittest
from pathlib import Path
from spending import Ledger,BudgetError

class BoundedLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.profile=dict(campaign_limit_microcny=1000000,task_limit_microcny=450000,input_ceiling_tokens=128000,
            max_output_tokens=16384,requests_per_task=2,jobs=['one','two'],endpoint='fixture',model='fixture')
        self.ledger=Ledger(Path(self.tmp.name)/'spending.sqlite',self.profile)
    def reserve(self,id,job='one'):
        return self.ledger.reserve(dict(id=id,job=job,arm='native-kz',endpoint='fixture',model='fixture',max_tokens=16384))
    def test_task_limit_does_not_reset_ledger_or_block_other_task(self):
        self.reserve('a');self.ledger.settle(dict(id='a',tokens=100000))
        with self.assertRaisesRegex(BudgetError,'per_task_budget'):self.reserve('b')
        self.assertIsNone(self.ledger.status()['halt_reason']);self.reserve('c','two')
    def test_unknown_usage_retains_maximum_but_allows_next_task(self):
        self.reserve('a');result=self.ledger.settle(dict(id='a',tokens=None))
        self.assertEqual(self.ledger.status()['uncertain_microcny'],387072)
        self.assertEqual(result['task_halt_reason'],'usage_unavailable')
        self.assertIsNone(result['halt_reason']);self.reserve('b','two')
    def test_http_attempt_limit_is_per_task_including_retries(self):
        for id in ('a','b'):self.reserve(id);self.ledger.settle(dict(id=id,tokens=1))
        with self.assertRaisesRegex(BudgetError,'per_task_request'):self.reserve('c')
        self.reserve('d','two')
    def test_closed_job_list_rejects_unplanned_calls(self):
        with self.assertRaisesRegex(BudgetError,'job_not_authorized'):self.reserve('a','unexpected')
    def test_restart_keeps_uncertain_amounts(self):
        self.reserve('a');self.ledger.reconcile_restart()
        reopened=Ledger(self.ledger.path,self.profile)
        self.assertEqual(reopened.status()['uncertain_microcny'],387072)
        with self.assertRaises(BudgetError):self.reserve('a')
        self.assertIsNone(reopened.status()['halt_reason']);self.reserve('b','two')
    def test_provider_failure_is_local_but_total_cap_stops_campaign(self):
        self.ledger.halt('provider_credentials','one')
        self.assertIsNone(self.ledger.status()['halt_reason']);self.reserve('a','two')
        self.ledger.halt('campaign_budget_exhausted','one')
        with self.assertRaisesRegex(BudgetError,'campaign_budget_exhausted'):self.reserve('b','one')

if __name__=='__main__':unittest.main()
