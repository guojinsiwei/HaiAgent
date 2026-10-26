import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harness'))
from android_ready import wait_ready

class ReadyTests(unittest.TestCase):
    def test_offline_during_root_recovers_before_admitting_task(self):
        root_calls=[]
        def run(cmd,**kwargs):
            command=cmd[3:]
            if command==['root']:
                root_calls.append(1)
                if len(root_calls)==1:raise subprocess.CalledProcessError(1,cmd)
            answers={('get-state',):'device',('shell','getprop','sys.boot_completed'):'1',
                ('shell','id','-u'):'0',('shell','service','check','package'):'Service package: found'}
            return Mock(stdout=answers.get(tuple(command),''))
        with tempfile.TemporaryDirectory() as d,patch('android_ready.subprocess.run',side_effect=run),patch('android_ready.time.sleep'):
            wait_ready(Mock(poll=lambda:None),d)
            proof=json.loads(Path(d,'adb-readiness.json').read_text())
            self.assertEqual(proof['attempt'],2);self.assertEqual(proof['stable_samples'],3)
    def test_permanent_offline_is_bounded_and_never_passes(self):
        with tempfile.TemporaryDirectory() as d,patch('android_ready.subprocess.run',side_effect=subprocess.TimeoutExpired('adb',30)) as run,patch('android_ready.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'four bounded'):wait_ready(Mock(poll=lambda:None),d)
            self.assertEqual(run.call_count,4);self.assertFalse(Path(d,'adb-readiness.json').exists())

if __name__=='__main__':unittest.main()
