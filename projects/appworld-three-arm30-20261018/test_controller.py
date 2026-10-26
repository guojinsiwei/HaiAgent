import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import runner
class ControllerTests(unittest.TestCase):
    def test_single_trial_exception_does_not_cancel_other_119(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);arms=['hld','kzdsh-new','recuris','dsh'];tasks=[{'task':str(i)} for i in range(30)]
            (root/'budget-profile.json').write_text(json.dumps({'campaign_limit_microcny':720000000,'task_limit_microcny':8000000}))
            called=[]
            def trial(row,key,arm,ledger):
                called.append((row['task'],arm))
                if row['task']=='0' and arm=='recuris':raise RuntimeError('injected isolated failure')
                return {'task':row['task'],'arm':arm,'state':'graded'}
            sleep=time.sleep
            with patch.object(runner,'R',root),patch.object(runner,'validate',lambda:{'tasks':tasks,'methods':arms}),patch.object(runner,'trial',trial),patch.object(runner.time,'sleep',lambda _:sleep(.001)),patch.object(runner.shutil,'disk_usage',lambda _:type('Space',(),{'free':100*2**30})()):
                runner.campaign('offline')
            data=json.loads((root/'summary.json').read_text())
            self.assertEqual(len(set(called)),120)
            self.assertEqual(sum(r['state']=='graded' for r in data['completed']),119)
            self.assertEqual(data['state'],'complete_with_engineering_failures')
    def test_no_new_trials_when_campaign_budget_is_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'budget-profile.json').write_text(json.dumps({'campaign_limit_microcny':1,'task_limit_microcny':1}))
            with patch.object(runner,'R',root),patch.object(runner,'validate',lambda:{'tasks':[{'task':'a'}],'methods':['hld','kzdsh-new','recuris','dsh']}),patch.object(runner,'trial') as trial:
                runner.campaign('offline');trial.assert_not_called()
            data=json.loads((root/'summary.json').read_text())
            self.assertEqual([r['state'] for r in data['completed']],['not_run_budget']*4)
if __name__=='__main__':unittest.main()
