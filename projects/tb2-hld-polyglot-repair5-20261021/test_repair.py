import json
from pathlib import Path
import tempfile
import unittest
from repair_driver import free_slots, frozen_results_intact, R, ORIGINAL, rows_to_retry
from spending import Ledger, BudgetError


class RepairSafety(unittest.TestCase):
    def test_main_and_existing_repairs_reserve_all_pending_capacity(self):
        main = {'rows': [{'state': 'running'}]*6}
        other = {'rows': [{'state': 'running'}]*2 + [{'state': 'pending'}]}
        self.assertEqual(free_slots(main, other, 0), 0)
        main['rows'].pop()
        self.assertEqual(free_slots(main, other, 0), 0)
        other['rows'].pop()
        self.assertEqual(free_slots(main, other, 0), 1)
        self.assertEqual(free_slots(main, other, 1), 0)

    def test_same_job_cumulative_budget_is_not_reset(self):
        profile = json.loads((ORIGINAL/'budget-profile.json').read_text())
        row, = rows_to_retry()
        self.assertEqual(row['budget_job'], 'tb2hr39-34-hld-polyglot-rust-c')
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder)/'spending.sqlite', profile)
            with ledger.db() as db:
                db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',
                           ('prior', row['budget_job'], 'kz', 7900000, 7900000, 'settled', 1.0))
            request = dict(id='retry', job=row['budget_job'], arm='kz', endpoint=profile['endpoint'],
                           model=profile['model'], max_tokens=profile['max_output_tokens'])
            with self.assertRaises(BudgetError) as caught:
                ledger.reserve(request)
            self.assertEqual(caught.exception.reason, 'per_task_budget_exhausted')
            self.assertEqual(ledger.status()['settled_microcny'], 7900000)

    def test_historical_results_and_profile_preserved(self):
        self.assertTrue(frozen_results_intact())
        self.assertEqual(json.loads((R/'budget-profile.json').read_text()),
                         json.loads((ORIGINAL/'budget-profile.json').read_text()))


if __name__ == '__main__':
    unittest.main()
