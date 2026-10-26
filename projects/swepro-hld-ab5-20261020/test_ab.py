import unittest,json,hashlib
from pathlib import Path
import runner,ab_controller
class Tests(unittest.TestCase):
 def test_same_budget_model_runtime_and_hld_entrypoint(self):
  p=runner.read(runner.R/'budget-profile.json')
  self.assertEqual(p['task_limit_microcny'],8000000);self.assertEqual(p['campaign_limit_microcny'],80000000)
  self.assertEqual(len(p['jobs']),10);self.assertEqual(p['solver_seconds'],3000)
  class B:token='offline'
  for arm in ['old','new']:
   payload=runner.payload_for(arm,'swp-05-'+arm,'original public task',B(),'dummy')
   self.assertEqual(payload['arm'],'hld');self.assertEqual(payload['spending']['CAMPAIGN_BUDGET_ARM'],'kz')
   self.assertEqual(payload['spending']['CAMPAIGN_BUDGET_JOB'],'swp-05-'+arm)
 def test_variant_mount_is_the_only_mount_difference_and_answers_are_absent(self):
  class S:root=runner.R/'relays/offline'
  old=runner.install_mounts(S(),'old');new=runner.install_mounts(S(),'new')
  changes=[(a,b) for a,b in zip(old,new) if a!=b]
  self.assertEqual(len(changes),1)
  self.assertEqual(changes[0][0][1],'/opt/kz')
  self.assertEqual(changes[0][0][0].name,'kz');self.assertEqual(changes[0][1][0].name,'hld-new')
  for src,dst,ro in old+new:
   self.assertTrue(ro);self.assertNotIn('/tasks/',str(src));self.assertNotIn('/jobs/',str(src));self.assertNotIn('/audit/',str(src))
 def test_sources_frozen_original_ledger_unchanged_and_preflight_is_keyless(self):
  runner.freeze_validate();ab_controller.admission()
  ready=runner.read(runner.R/'preflight-ready.json')
  self.assertTrue(ready['passed']);self.assertEqual(ready['model_calls'],0)
  a=runner.read(runner.R/'budget-allocation.json');self.assertLessEqual(a['combined_max_microcny'],240000000)
  selection=runner.read(runner.R/'selection.json')
  self.assertEqual(set(selection['indices']),{5,8,11,12,10})
  self.assertEqual(selection['seed'],20261020)
if __name__=='__main__':unittest.main()
