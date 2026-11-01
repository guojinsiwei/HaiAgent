import unittest
from regrade_outer_clock import repair_run

class ClockTests(unittest.TestCase):
    def test_only_external_suite_clock_changes(self):
        calls=[]
        def original(argv,**kw):calls.append((argv,kw));return 'ok'
        wrapped=repair_run(original)
        self.assertEqual(wrapped(['docker','exec','owned','timeout','300','bash','/tests/run-tests.sh'],timeout=360),'ok')
        self.assertEqual(calls[0][0],['docker','exec','owned','timeout','900','bash','/tests/run-tests.sh'])
        self.assertEqual(calls[0][1]['timeout'],960)

    def test_other_docker_commands_unchanged(self):
        calls=[]
        wrapped=repair_run(lambda argv,**kw:calls.append((argv,kw)))
        wrapped(['docker','exec','owned','python3','/tests/f2p.py'],timeout=120)
        self.assertEqual(calls[0],(['docker','exec','owned','python3','/tests/f2p.py'],dict(timeout=120)))

if __name__=='__main__':unittest.main()
