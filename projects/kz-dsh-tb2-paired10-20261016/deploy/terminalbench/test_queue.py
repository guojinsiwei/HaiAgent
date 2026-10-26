import unittest
from queue_policy import initial_rows,finish,candidates,first_finished,append_retry_batch,summary
class QueueTests(unittest.TestCase):
    def test_paired_alternation_and_single_active(self):
        rows=initial_rows(['a','b'],{})
        self.assertEqual([(r['task'],r['arm']) for r in rows],[('a','dsh'),('a','kz-dsh'),('b','kz-dsh'),('b','dsh')])
        self.assertEqual(candidates(rows,set()),[rows[0]])
        self.assertEqual(candidates(rows,{'dsh'}),[])
        self.assertEqual(candidates(rows,{'kz-dsh'}),[])
    def test_fault_and_budget_exhaustion_continue_without_free_retries(self):
        rows=initial_rows(['a','b'],{})
        for i,row in enumerate(rows):
            self.assertEqual(candidates(rows,set()),[row])
            finish(row,dict(engineering_clean=i!=0,reward=int(i==3),completion='budget_exhausted' if i==1 else None))
            self.assertFalse(append_retry_batch(rows))
        self.assertTrue(first_finished(rows));self.assertEqual(len(rows),4)
        self.assertEqual(summary(rows)['dsh']['passed'],1)
        self.assertEqual(summary(rows)['kz-dsh']['passed'],0)
    def test_history_never_reused(self):
        rows=initial_rows(['a'],{'a':{'attempted':True,'engineering_clean':True}})
        self.assertTrue(all(r['state']=='pending' for r in rows))
if __name__=='__main__':unittest.main()
