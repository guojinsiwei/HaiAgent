import tempfile,unittest
from pathlib import Path
from circuit import Circuit,provider_fault

class Tests(unittest.TestCase):
    def test_outage_blocks_queue_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            now=[100.0];p=Path(tmp)/'circuit.sqlite'
            c=Circuit(p,clock=lambda:now[0],cooldown=60,success_gap=10)
            self.assertFalse(c.admit())
            for _ in range(3):
                generation=c.probe_ticket();self.assertIsNotNone(generation)
                c.success(generation);now[0]+=10
            self.assertTrue(c.success(generation,paid_canary=True));self.assertTrue(c.admit())
            c.fail('transport');self.assertFalse(c.admit())
            self.assertFalse(Circuit(p).admit());self.assertIsNone(c.probe_ticket())
    def test_concurrent_failure_invalidates_successful_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Circuit(Path(tmp)/'s.sqlite',clock=lambda:100)
            ticket=c.probe_ticket();c.fail('new failure')
            self.assertFalse(c.success(ticket,paid_canary=True));self.assertFalse(c.admit())
    def test_score_does_not_hide_transport(self):
        self.assertTrue(provider_fault({'reward':.7,'engineering_clean':True,'stops':{'provider-stop.json':{'kind':'transport'}}}))
        self.assertFalse(provider_fault({'reward':0,'stops':{'budget-stop.json':{'reason':'per_task_budget_exhausted'}}}))
        self.assertTrue(provider_fault({'reward':1,'budget_stop':{'reason':'usage_unavailable'}}))

if __name__=='__main__':unittest.main()
