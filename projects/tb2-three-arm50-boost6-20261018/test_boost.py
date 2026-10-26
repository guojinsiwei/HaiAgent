import copy,unittest
from boost import make_rows,select
class Tests(unittest.TestCase):
 def fixture(self):
  rows=[dict(job=str(i),budget_job='budget'+str(i),task='task',arm=['kz-dsh','dsh','native-kz'][i%3],state='pending') for i in range(12)]
  rows[0]['state']='running';rows[1]['state']='preflighting'
  return dict(rows=rows,active=[dict(job='0',offline=False),dict(job='1',offline=True)])
 def test_combined_six_and_two_per_arm(self):
  h=self.fixture();rows=make_rows(h);chosen=select(rows,[],h)
  self.assertEqual(len(chosen),4)
  self.assertFalse(any(r['previous_job'] in ('0','1') for r in chosen))
  self.assertEqual(sorted(r['arm'] for r in chosen),sorted(['native-kz','native-kz','kz-dsh','dsh']))
 def test_active_paid_not_repeated_and_offline_pending_released(self):
  h=self.fixture();rows=make_rows(h)
  h['active']=[];h['rows'][0].update(state='done',engineering_clean=True,result={'reward':1});h['rows'][1]['state']='pending'
  chosen=select(rows,[],h)
  self.assertEqual(rows[0]['state'],'historical');self.assertTrue(rows[0]['inherited'])
  self.assertEqual(rows[1]['state'],'pending');self.assertIn(rows[1],chosen)
 def test_unconfirmed_preflight_not_released(self):
  h=self.fixture();rows=make_rows(h);h['active']=[];h['rows'][1]['state']='pending'
  select(rows,[],h,lambda r:False)
  self.assertEqual(rows[1]['state'],'waiting_previous')
 def test_never_exceeds_current_total(self):
  h=self.fixture();rows=make_rows(h)
  self.assertEqual(len(select(rows,['native-kz','native-kz','kz-dsh','dsh'],h)),0)
if __name__=='__main__':unittest.main()
