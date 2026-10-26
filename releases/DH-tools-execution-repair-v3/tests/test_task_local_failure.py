"""Single-task context errors are not campaign-wide infrastructure failures."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import environment
from runner import failure_scope

class FailureTests(unittest.TestCase):
    def test_context_error_does_not_stop_other_workers(self):
        flags=failure_scope('context_budget_error')
        self.assertEqual(flags['task_local_error'],'context_budget_error')
        self.assertFalse(flags.get('engineering_fault'))
    def test_shared_infrastructure_failure_keeps_stop_loss(self):
        for reason in ('credential_or_balance_error',):
            self.assertEqual(failure_scope(reason),{'engineering_fault':reason})
        self.assertEqual(failure_scope('infrastructure_error','SharedBackendError'),
                         {'engineering_fault':'infrastructure_error'})
    def test_driver_container_and_delivery_failures_are_local(self):
        for reason,kind in [('infrastructure_error','TaskBackendError'),
                            ('infrastructure_error','RuntimeError'),('delivery_error',None)]:
            flags=failure_scope(reason,kind)
            self.assertIn('task_local_error',flags)
            self.assertNotIn('engineering_fault',flags)

if __name__=='__main__':unittest.main()
