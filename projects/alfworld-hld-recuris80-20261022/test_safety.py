from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
import runner
from spending import Ledger,BudgetError


class Safety(unittest.TestCase):
    def test_other_queues_reserved_against_total_twelve(self):
        states=[{'rows':[{'state':'running'}]*3},{'rows':[{'state':'running'}]*2+[{'state':'pending'}]},
                {'rows':[{'state':'running'}]}]
        with patch.object(runner,'read',side_effect=states):self.assertEqual(runner.available_slots(0),5)
        with patch.object(runner,'read',side_effect=states):self.assertEqual(runner.available_slots(5),0)

    def test_seven_yuan_cumulative_cap(self):
        profile=runner.read(runner.R/'budget-profile.json');job=profile['jobs'][0]
        with tempfile.TemporaryDirectory() as d:
            ledger=Ledger(Path(d)/'budget.sqlite',profile)
            with ledger.db() as db:db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('old',job,'kz',6900000,6900000,'settled',1.))
            with self.assertRaises(BudgetError):ledger.reserve(dict(id='next',job=job,arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=16384))
            self.assertEqual(ledger.status()['settled_microcny'],6900000)

    def test_manifest_unique_and_balanced_pairs(self):
        m=runner.read(runner.R/'manifest.json');p=runner.read(runner.R/'budget-profile.json')
        self.assertEqual(len(m['selected']),80);self.assertEqual(len({r['id'] for r in m['selected']}),80)
        self.assertEqual(len(p['jobs']),160);self.assertEqual(len(set(p['jobs'])),160)
        self.assertEqual(p['campaign_limit_microcny'],1120000000)
        self.assertEqual({r['type'] for r in m['selected']},{r['type'] for r in m['preflight_training']})


if __name__=='__main__':unittest.main()
