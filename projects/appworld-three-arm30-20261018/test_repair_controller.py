import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import runner_repair as runner
from spending import Ledger
class ResumeController(unittest.TestCase):
    def test_resume_preserves_old_spend_and_continues_after_one_failed_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            profile=dict(campaign_limit_microcny=720000000,task_limit_microcny=8000000,input_ceiling_tokens=128000,max_output_tokens=16384,requests_per_task=400,jobs=['old','hld--a--repair1','dsh--b'],endpoint='fixture',model='fixture')
            (root/'budget-profile.json').write_text(json.dumps(profile))
            ledger=Ledger(root/'spending.sqlite',profile)
            ledger.reserve(dict(id='old-call',job='old',arm='kz',endpoint='fixture',model='fixture',max_tokens=16384));ledger.settle(dict(id='old-call',tokens=123456))
            previous=[{'task':'old','arm':'hld','state':'graded','official_success':True}]
            plan={'previous_completed':previous,'queue':[{'arm':'hld','row':{'task':'a','_job':'hld--a--repair1'}},{'arm':'dsh','row':{'task':'b'}}]}
            seen=[]
            def trial(row,key,arm,ledger):
                seen.append(row['task'])
                if row['task']=='a':raise RuntimeError('isolated fixture')
                return {'task':row['task'],'arm':arm,'state':'graded','official_success':True}
            sleep=time.sleep
            with patch.object(runner,'R',root),patch.object(runner,'validate',lambda:plan),patch.object(runner,'trial',trial),patch.object(runner.time,'sleep',lambda _:sleep(.001)),patch.object(runner.shutil,'disk_usage',lambda _:type('Space',(),{'free':100*2**30})()):runner.campaign('offline')
            result=json.loads((root/'summary.json').read_text())
            self.assertEqual(set(seen),{'a','b'});self.assertEqual(len(result['completed']),3)
            self.assertEqual(result['budget']['settled_microcny'],123456)
            self.assertEqual(result['completed'][0],previous[0]);self.assertEqual(result['state'],'complete_with_engineering_failures')
if __name__=='__main__':unittest.main()
