import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from python.shared_budget import SharedBudget


class SharedBudgetTests(unittest.TestCase):
    def test_concurrent_reservations_and_restart_do_not_exceed_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=dict(path=str(Path(folder)/'budget.sqlite'),bucket='task/suz',total_limit_cny=3,bucket_limit_cny=2)
            SharedBudget(cfg)
            def reserve(_):
                try:return SharedBudget(cfg).reserve('solver',1)
                except ValueError:return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                ids=list(pool.map(reserve,range(8)))
            self.assertEqual(sum(x is not None for x in ids),2)
            recovered=SharedBudget(cfg)
            with self.assertRaises(ValueError):recovered.reserve('critic',0.1)
            recovered.settle(next(x for x in ids if x),0.2)
            self.assertTrue(recovered.reserve('critic',0.8))
            other=SharedBudget({**cfg,'bucket':'task/baseline'})
            self.assertTrue(other.reserve('solver',1))
            with self.assertRaises(ValueError):other.reserve('solver',0.01)

    def test_existing_limits_cannot_be_expanded(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=dict(path=str(Path(folder)/'budget.sqlite'),bucket='probe',total_limit_cny=320,bucket_limit_cny=1)
            SharedBudget(cfg)
            with self.assertRaises(ValueError):SharedBudget({**cfg,'total_limit_cny':640})
