import concurrent.futures,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'SUZ-repair4'))
from python.shared_budget import SharedBudget

class BudgetTests(unittest.TestCase):
    def test_parallel_combined_budget_and_same_task_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            def budget(bucket):return SharedBudget({'path':str(Path(directory)/'budget.sqlite'),'bucket':bucket,'total_limit_cny':320,'bucket_limit_cny':8})
            first=budget('webarena/suz/1');first.reserve('solver',5);first.reserve('critic',3)
            with self.assertRaises(ValueError):first.reserve('advisor',.01)
            def fill(i):
                try:budget('androidworld/baseline/'+str(i)).reserve('solver',8);return True
                except ValueError:return False
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:result=list(pool.map(fill,range(50)))
            self.assertEqual(sum(result),39)
            with self.assertRaises(ValueError):budget('new').reserve('solver',.01)
            with self.assertRaises(ValueError):SharedBudget({'path':str(Path(directory)/'budget.sqlite'),'bucket':'new','total_limit_cny':480,'bucket_limit_cny':8})

if __name__=='__main__':unittest.main()
