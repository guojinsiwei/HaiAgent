import unittest,json,tempfile
from pathlib import Path
from queue_policy import initial_rows,candidates,finish,summary
from spending import Ledger,BudgetError
R=Path(__file__).resolve().parent
class Checks(unittest.TestCase):
 def test_pair_and_isolation(self):
  rows=initial_rows([str(i) for i in range(7)],{})
  self.assertEqual(len(rows),14);finish(rows[0],{'engineering_clean':False,'reason':'synthetic_failure'})
  picked=candidates(rows,[]);self.assertEqual(len(picked),4);self.assertNotIn(rows[0],picked)
  self.assertEqual(sum(r['arm']=='hld' for r in picked),2)
  self.assertEqual(sum(r['arm']=='recuris' for r in picked),2)
 def test_independent_caps(self):
  p=json.loads((R/'budget-profile.json').read_text());self.assertEqual(p['campaign_limit_microcny'],84000000);self.assertEqual(p['task_limit_microcny'],6000000)
  with tempfile.TemporaryDirectory() as d:
   l=Ledger(Path(d)/'test.db',p)
   for i in range(15):
    q={'id':str(i),'job':p['jobs'][0],'arm':'kz','endpoint':p['endpoint'],'model':p['model'],'max_tokens':16384};l.reserve(q);l.settle({'id':str(i),'tokens':387072})
   with self.assertRaises(BudgetError):l.reserve({**q,'id':'over'})
   l.reserve({**q,'id':'other','job':p['jobs'][1]})
   self.assertLessEqual(l.status()['settled_microcny']+l.status()['reserved_microcny'],84000000)
if __name__=='__main__':unittest.main()
