import json,unittest
from pathlib import Path
from common import ROOT,SOURCE,config

class FreshRoundTests(unittest.TestCase):
    def test_exactly_thirty_identical_unique_tasks_per_arm(self):
        jobs=json.loads((ROOT/'jobs.json').read_text())
        rows=json.loads((ROOT/'task-manifest.json').read_text())['tasks']
        self.assertEqual(len(rows),30);self.assertEqual(len(jobs),60)
        self.assertEqual(len({(x['mode'],x['id']) for x in jobs}),60)
        for mode in ['suz','opencua_baseline']:
            self.assertEqual({x['id'] for x in jobs if x['mode']==mode},{x['id'] for x in rows})
        self.assertEqual({x['mode'] for x in jobs[:2]},{'suz','opencua_baseline'})

    def test_budget_is_new_local_ledger_and_identical_model_limits(self):
        self.assertTrue(SOURCE.is_dir())
        a=config('test','suz');b=config('test','opencua_baseline')
        self.assertEqual(Path(a['shared_budget']['path']),ROOT/'budget.sqlite')
        self.assertNotEqual(Path(a['shared_budget']['path']),ROOT.parent/'budget.sqlite')
        self.assertEqual(a['shared_budget']['total_limit_cny'],480)
        self.assertEqual(a['shared_budget']['bucket_limit_cny'],8)
        for key in ['solver_model','role_model','max_steps','max_requests','max_seconds','budget_cny','max_output_tokens','request_timeout']:
            self.assertEqual(a[key],b[key])
        self.assertFalse(a['server_gpu_allowed'])

if __name__=='__main__':unittest.main()
