import unittest,json,hashlib
from pathlib import Path
from collections import Counter
import queue_policy
R=Path(__file__).resolve().parent
class CompareContract(unittest.TestCase):
 def test_twenty_distinct_jobs_same_ten_tasks(self):
  tasks=json.loads((R/'tasks.json').read_text())['tasks'];rows=queue_policy.initial_rows([x['name'] for x in tasks],{})
  self.assertEqual(len(rows),20);self.assertEqual(len({x['job'] for x in rows}),20)
  self.assertEqual(Counter(x['task'] for x in rows),{x['name']:2 for x in tasks})
  self.assertEqual(Counter(x['arm'] for x in rows),{'hld-old':10,'hld-new':10})
 def test_isolated_failure_and_balanced_concurrency(self):
  rows=queue_policy.initial_rows([str(i) for i in range(10)],{})
  queue_policy.finish(rows[0],{'engineering_clean':False})
  selected=queue_policy.candidates(rows,[])
  self.assertEqual(len(selected),4);self.assertNotIn(rows[0],selected)
  self.assertEqual(Counter(r['arm'] for r in selected),{'hld-old':2,'hld-new':2})
  self.assertFalse(queue_policy.append_retry_batch(rows))
 def test_frozen_budget_and_model(self):
  p=json.loads((R/'budget-profile.json').read_text())
  self.assertEqual(p['task_limit_microcny'],4000000);self.assertEqual(p['campaign_limit_microcny'],80000000)
  self.assertEqual(p['model'],'deepseek-flash');self.assertEqual(len(p['jobs']),20)
 def test_baseline_source_unchanged_and_new_source_matches_tested(self):
  old=R.parent/'tb4-hld-recuris7-20261019/runtime/kz/src'
  for p in old.glob('*.mjs'):self.assertEqual(p.read_bytes(),(R/'bundle/hld-old/src'/p.name).read_bytes())
  for p in (R/'runtime/hld/src').glob('*.mjs'):self.assertEqual(p.read_bytes(),(R/'bundle/kz/src'/p.name).read_bytes())
 def test_frozen_official_tasks(self):
  manifest=json.loads((R/'dependencies/ready.json').read_text())
  for name,sha in manifest['files'].items():self.assertEqual(hashlib.sha256((R/'dependencies'/name).read_bytes()).hexdigest(),sha)
 def test_context_settings_have_room_for_full_solver_output(self):
  from yaml import safe_load
  old=safe_load((R/'bundle/kz/config/common.patch.yml').read_text())
  self.assertEqual(next(p['config']['maxTokens'] for p in old if p['id']=='compaction-basic'),16384)
  patch=safe_load((R/'bundle/kz/.runtime/hld-new-context.patch.yml').read_text())[0]['config']
  self.assertEqual(patch,{'headroomTokens':16384,'maxTokens':4096})
  self.assertEqual(min(int(128000*.8),128000-16384-patch['headroomTokens']),95232)
  self.assertLess(int((128000-16384)*.16),95232)
if __name__=='__main__':unittest.main()
