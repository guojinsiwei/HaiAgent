import json
from pathlib import Path
import tempfile
import unittest
from repair_driver import free_slots, frozen_results_intact, R, ORIGINAL
from spending import Ledger, BudgetError


class RepairSafety(unittest.TestCase):
    def test_main_preflight_to_paid_still_reserves_slot(self):
        main = {'rows': [{'state': 'preflighting'}] + [{'state': 'running'}]*7}
        self.assertEqual(free_slots(main, 0), 0)
        main['rows'][0]['state'] = 'pending'
        self.assertEqual(free_slots(main, 0), 0)

    def test_repair_uses_only_unfillable_main_capacity(self):
        main = {'rows': [{'state': 'running'}]*6 + [{'state': 'pending'}]}
        self.assertEqual(free_slots(main, 0), 1)
        self.assertEqual(free_slots(main, 1), 0)

    def test_same_job_retains_existing_charge(self):
        profile = json.loads((ORIGINAL/'budget-profile.json').read_text())
        job = 'tb2hr39-04-recuris-caffe-cifar-10'
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder)/'spending.sqlite', profile)
            with ledger.db() as db:
                db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',
                           ('prior', job, 'dsh', 7900000, 7900000, 'settled', 1.0))
            request = dict(id='retry', job=job, arm='dsh', endpoint=profile['endpoint'],
                           model=profile['model'], max_tokens=profile['max_output_tokens'])
            with self.assertRaises(BudgetError) as caught:
                ledger.reserve(request)
            self.assertEqual(caught.exception.reason, 'per_task_budget_exhausted')
            self.assertEqual(ledger.status()['settled_microcny'], 7900000)

    def test_source_results_and_profile_preserved(self):
        self.assertTrue(frozen_results_intact())
        self.assertEqual(json.loads((R/'budget-profile.json').read_text()),
                         json.loads((ORIGINAL/'budget-profile.json').read_text()))


if __name__ == '__main__':
    unittest.main()
