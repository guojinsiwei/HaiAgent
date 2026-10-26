import unittest
from queue_policy import *
class QueueTests(unittest.TestCase):
 def test_exact_faults_only(self):
  rows=initial_rows(list({t for t,a in AUTHORIZED}),{})
  self.assertEqual([(r['task'],r['arm']) for r in rows],AUTHORIZED)
  self.assertEqual(len({r['job'] for r in rows}),1)
  self.assertEqual(sum(r['arm']=='dsh' for r in rows),1)
  with self.assertRaises(ValueError):initial_rows(['unapproved'],{})
 def test_single_authorized_retry_and_fault_isolation(self):
  rows=initial_rows(list({t for t,a in AUTHORIZED}),{})
  first=candidates(rows,set());self.assertEqual(len(first),1);self.assertEqual({r['arm'] for r in first},{'dsh'})
  self.assertEqual(candidates(rows,{'dsh','kz-dsh'}),[])
  finish(first[0],dict(engineering_clean=False));self.assertFalse(append_retry_batch(rows))
  self.assertEqual(candidates(rows,{'dsh'}),[])
  for r in rows:
   if r['state']=='pending':finish(r,dict(engineering_clean=True,reward=0))
  self.assertTrue(first_finished(rows));self.assertEqual(len(rows),1)
if __name__=='__main__':unittest.main()
