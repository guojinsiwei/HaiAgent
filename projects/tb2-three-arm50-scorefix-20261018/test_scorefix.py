import json,tempfile,types,unittest
from pathlib import Path
from verifier_setup import validate_test_report,VerifierInfrastructureError
from score_retry import make_rows,candidates
class Tests(unittest.TestCase):
 def test_reports(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);v=types.SimpleNamespace(trial_paths=types.SimpleNamespace(verifier_dir=p))
   with self.assertRaises(VerifierInfrastructureError):validate_test_report(v)
   (p/'ctrf.json').write_text(json.dumps({'results':{'summary':{'tests':0},'tests':[]}}))
   with self.assertRaises(VerifierInfrastructureError):validate_test_report(v)
   (p/'ctrf.json').write_text(json.dumps({'results':{'summary':{'tests':1},'tests':[{'status':'failed'}]}}));(p/'reward.txt').write_text('0')
   validate_test_report(v)
   (p/'reward.txt').write_text('1')
   with self.assertRaises(VerifierInfrastructureError):validate_test_report(v)
 def test_replay_never_paid(self):
  root=Path(__file__).resolve().parent;plan=json.loads((root/'repair-plan.json').read_text())
  rows=make_rows(plan,{'results':[{'task':'torch-pipeline-parallelism','reward':0,'engineering_clean':True}]})
  r=next(r for r in rows if r.get('score_only'));self.assertEqual(r['state'],'done');self.assertNotIn(r,candidates(rows,[]))
  self.assertEqual({r['budget_job'] for r in rows},{r['budget_job'] for r in plan})
  chosen=candidates(rows,[]);self.assertEqual(len(chosen),6)
  self.assertTrue(all(sum(r['arm']==a for r in chosen)==2 for a in ['dsh','native-kz','kz-dsh']))
 def test_reject_paid_rerun(self):
  root=Path(__file__).resolve().parent;plan=json.loads((root/'repair-plan.json').read_text());plan[1]['result']['paid_calls']=1
  with self.assertRaises(AssertionError):make_rows(plan,{'results':[{'task':'torch-pipeline-parallelism','reward':0}]})
if __name__=='__main__':unittest.main()
