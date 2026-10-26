import json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
import runner
class ControllerTests(unittest.TestCase):
 def test_budget_stop_is_a_valid_limit_not_an_unclassified_process_fault(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);(p/'audit/kz').mkdir(parents=True)
   (p/'audit/budget-stop.json').write_text(json.dumps(dict(reason='per_task_budget_exhausted')))
   (p/'audit/shared-state.json').write_text(json.dumps(dict(requests=27,tools=39)))
   result=runner.progress(p)
   self.assertTrue(result['budget_exhausted']);self.assertEqual(result['shared_requests'],27);self.assertEqual(result['tools'],39)
 def test_unknown_usage_remains_an_engineering_stop_not_a_normal_limit(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);(p/'audit/kz').mkdir(parents=True)
   (p/'audit/budget-stop.json').write_text(json.dumps(dict(reason='usage_unavailable')))
   self.assertFalse(runner.progress(p)['budget_exhausted'])
 def test_one_worker_exception_does_not_cancel_the_remaining_eleven_runs(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);rows=[dict(task=str(i)) for i in range(6)];jobs=[a+'--'+r['task'] for r in rows for a in ['baseline','candidate']]
   profile=dict(campaign_limit_microcny=48000000,task_limit_microcny=4000000,jobs=jobs)
   (root/'budget-profile.json').write_text(json.dumps(profile));called=[]
   def trial(row,key,arm,ledger):
    called.append((row['task'],arm))
    if row['task']=='0' and arm=='baseline':raise RuntimeError('isolated simulated failure')
    return dict(task=row['task'],arm=arm,state='graded')
   sleep=time.sleep
   with patch.object(runner,'ROOT',root),patch.object(runner,'validate',lambda:dict(tasks=rows)),patch.object(runner,'trial',trial),patch.object(runner.time,'sleep',lambda _:sleep(.001)),patch.object(runner.shutil,'disk_usage',lambda _:type('Space',(),dict(free=100*2**30))()):
    runner.campaign('offline-no-credential')
   result=json.loads((root/'summary.json').read_text())
   self.assertEqual(len(called),12);self.assertEqual(len(set(called)),12)
   self.assertEqual(sum(x['state']=='graded' for x in result['completed']),11)
   self.assertEqual(result['state'],'complete_with_engineering_failures')
if __name__=='__main__':unittest.main()
