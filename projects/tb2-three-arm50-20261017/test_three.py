import json,tempfile,unittest,concurrent.futures
from pathlib import Path
from queue_policy import initial_rows,candidates,finish,summary,ARMS
from spending import Ledger,BudgetError
class ThreeTests(unittest.TestCase):
    def test_full_design_and_failure_isolation(self):
        rows=initial_rows([f't{i}' for i in range(50)],{})
        self.assertEqual(len(rows),150);self.assertEqual(len({r['job'] for r in rows}),150)
        self.assertEqual([r['arm'] for r in candidates(rows,[])],['native-kz','kz-dsh','dsh','kz-dsh','dsh','native-kz'])
        finish(rows[0],dict(engineering_clean=False))
        self.assertEqual(len(candidates(rows,[])),6)
        for arm in ARMS:self.assertEqual(summary(rows)[arm]['total'],50)
        self.assertTrue(all(r['arm']!='native-kz' for r in candidates(rows,['native-kz']*2)))
    def test_parallel_budget_cannot_overspend(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile=dict(campaign_limit_microcny=600000,task_limit_microcny=400000,input_ceiling_tokens=128000,max_output_tokens=16384,requests_per_task=120,jobs=['a','b','c'],endpoint='fixture',model='fixture')
            ledger=Ledger(Path(tmp)/'spending.sqlite',profile)
            def reserve(n):
                try:ledger.reserve(dict(id=n,job=n,arm='kz',endpoint='fixture',model='fixture',max_tokens=16384));return True
                except BudgetError:return False
            with concurrent.futures.ThreadPoolExecutor(3) as pool:results=list(pool.map(reserve,['a','b','c']))
            self.assertEqual(sum(results),1);self.assertGreaterEqual(ledger.status()['remaining_microcny'],0)
if __name__=='__main__':unittest.main()
