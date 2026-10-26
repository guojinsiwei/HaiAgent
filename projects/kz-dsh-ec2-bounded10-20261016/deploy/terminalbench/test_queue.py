import unittest
from queue_policy import initial_rows,finish,candidates,first_finished,append_retry_batch,summary

class QueueTests(unittest.TestCase):
    def test_faults_continue_all_tasks_then_retry_only_faults_once(self):
        rows=initial_rows([str(i) for i in range(30)],{})
        for i,row in enumerate(rows[:]):
            self.assertIn(row,candidates(rows,set()))
            finish(row,dict(engineering_clean=i not in (0,4),reward=0))
            if i<29:self.assertFalse(append_retry_batch(rows))
        self.assertTrue(first_finished(rows));self.assertTrue(append_retry_batch(rows))
        self.assertEqual([r['task'] for r in rows[30:]],['0','4'])
        self.assertFalse(append_retry_batch(rows))
        finish(rows[30],dict(engineering_clean=True,reward=0))
        finish(rows[31],dict(engineering_clean=False,reward=None))
        self.assertEqual(summary(rows)['kz-dsh'],dict(first_finished=30,total=30,retry_finished=2,retry_total=2,clean=29,passed=0))
        self.assertFalse(append_retry_batch(rows));self.assertEqual(candidates(rows,set()),[])
    def test_one_active_candidate_and_no_historical_score_reuse(self):
        rows=initial_rows(['a'],{'a':{'attempted':True,'engineering_clean':True}})
        self.assertEqual(rows[0]['state'],'pending')
        self.assertEqual(candidates(rows,{'kz-dsh'}),[])
    def test_budget_exhaustion_is_not_free_retry(self):
        rows=initial_rows(['a'],{});finish(rows[0],dict(engineering_clean=True,reward=0,completion='budget_exhausted'))
        append_retry_batch(rows);self.assertEqual(len(rows),1)

if __name__=='__main__':unittest.main()
