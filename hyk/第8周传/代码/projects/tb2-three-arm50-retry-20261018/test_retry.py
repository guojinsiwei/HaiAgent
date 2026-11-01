import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import retry
from spending import Ledger,BudgetError
class RetryTests(unittest.TestCase):
 def test_only_faults_with_original_budget_are_selected(self):
  rows=[dict(job='good',state='done'),dict(job='zero',state='done'),dict(job='exhausted',state='engineering_failure',result={}),dict(job='fault',task='t',arm='dsh',state='engineering_failure',result={}),dict(job='ambiguous',state='engineering_failure',result={'reason':'runner_receipt_missing_quarantined'})]
  selected,skipped=retry.select_rows({'rows':rows},lambda job:(1,3900000 if job=='exhausted' else 1000000),False)
  self.assertEqual([r['budget_job'] for r in selected],['fault'])
  self.assertEqual(selected[0]['remaining_microcny'],3000000)
  self.assertEqual(len(skipped),2)
 def test_concurrency_three_and_one_per_arm(self):
  rows=[dict(state='pending',arm=a) for a in ['native-kz','native-kz','kz-dsh','dsh','dsh']]
  self.assertEqual([r['arm'] for r in retry.candidates(rows,[])],['native-kz','kz-dsh','dsh'])
  self.assertEqual([r['arm'] for r in retry.candidates(rows,['dsh'])],['native-kz','kz-dsh'])
 def test_shared_ledger_keeps_inflight_and_original_charges(self):
  profile=retry.read(retry.R/'budget-profile.json');job=profile['jobs'][0]
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);(p/'budget-profile.json').write_text(json.dumps(profile))
   ledger=Ledger(p/'spending.sqlite',profile)
   request=dict(id='fixture-1',job=job,arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=profile['max_output_tokens'])
   ledger.reserve(request)
   with patch.object(retry,'P',p),patch.object(retry,'server_for',return_value=MagicMock()):
    service=retry.SharedBudget()
    self.assertEqual(service.snapshot()['reserved_microcny'],387072)
    self.assertEqual(service.snapshot()['uncertain_microcny'],0)
    ledger.settle(dict(id='fixture-1',tokens=3700000))
    with self.assertRaisesRegex(BudgetError,'per_task_budget_exhausted'):
     service.ledger.reserve(dict(request,id='fixture-2'))
    self.assertEqual(service.snapshot()['settled_microcny'],3700000)
if __name__=='__main__':unittest.main()
