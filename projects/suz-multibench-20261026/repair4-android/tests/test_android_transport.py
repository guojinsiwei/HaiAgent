import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harness'))
from android_transport import command_timeout

class TransportTests(unittest.TestCase):
    def test_cpu_app_start_timeout_floor(self):
        self.assertEqual(command_timeout(['shell','am','start','','-W','-n','app/activity'],5),45)
        self.assertEqual(command_timeout(['shell','monkey','-p','app','1'],5),45)
        self.assertEqual(command_timeout(['shell','am','start'],60),60)
    def test_other_commands_unchanged(self):
        self.assertEqual(command_timeout(['shell','input','tap','10','20'],5),5)
        self.assertIsNone(command_timeout(['root'],None))

if __name__=='__main__':unittest.main()
