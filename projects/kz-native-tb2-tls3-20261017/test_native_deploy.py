import sys,tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent/'native'))
from spending_client import cost_usage,SpendingClient,SpendingStopped
from queue_policy import initial_rows,candidates,finish,summary
from campaign import command
from entry_harbor import timeout

class DeploymentTests(unittest.TestCase):
    def test_timeout_recognizes_cli_name_and_import_path(self):
        for identity in ('Native','OfflineNative','OfflineTimeout'):
            for name,ip in [('agents:'+identity,None),(None,'agents:'+identity)]:
                self.assertIsNone(timeout(N(config=N(agent=N(name=name,import_path=ip)))))
    def test_cost_same_as_paired_peak_formula(self):
        self.assertEqual(cost_usage(dict(input_tokens=10,output_tokens=5,cache_read_input_tokens=20)),61)
        self.assertIsNone(cost_usage(dict(input_tokens=1)))
        self.assertIsNone(cost_usage(dict(input_tokens=-1,output_tokens=2)))
    def test_unknown_usage_stops_only_client(self):
        c=SpendingClient()
        with patch.object(c,'call',return_value={'task_halt_reason':'usage_unavailable'}):
            with self.assertRaisesRegex(SpendingStopped,'usage_unavailable'):c.settle('lease',None)
    def test_queue_continues_failed_trial_and_never_retries(self):
        rows=initial_rows(['a','b'],{})
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['arm'],'native-kz')
        self.assertEqual(candidates(rows,{'native-kz'}),[])
        finish(rows[0],dict(engineering_clean=False))
        self.assertEqual(candidates(rows,set()),[rows[1]])
        self.assertEqual(summary(rows)['native-kz']['first_finished'],1)
    def test_actual_command_uses_native_agent(self):
        r=dict(arm='native-kz',task='regex-log',job='fixture')
        self.assertIn('agents:Native',command(r,False));self.assertIn('agents:OfflineNative',command(r,True))
if __name__=='__main__':unittest.main()
