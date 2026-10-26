import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harness'))
from android_ui import fresh_hierarchy

class UIReadTests(unittest.TestCase):
    def test_transient_dump_failure_recovers_without_reading_stale_file(self):
        dumps=[];reads=[]
        def request(args):
            if args[1]=='uiautomator':
                dumps.append(args[-1])
                return 'ERROR: could not get idle state' if len(dumps)==1 else 'UI hierchary dumped to: '+args[-1]
            if args[1]=='cat':reads.append(args[-1]);return '<hierarchy><node text="fresh"/></hierarchy>'
            return ''
        self.assertIn('fresh',fresh_hierarchy(request,sleep=lambda _:None))
        self.assertEqual(reads,[dumps[1]])
        self.assertNotEqual(dumps[0],dumps[1])

    def test_bad_or_empty_xml_fails_closed(self):
        for xml in ['broken','<hierarchy/>']:
            dumps=[]
            def request(args):
                if args[1]=='uiautomator':dumps.append(args[-1]);return 'UI hierchary dumped to: '+args[-1]
                return xml if args[1]=='cat' else ''
            with self.assertRaises(RuntimeError):fresh_hierarchy(request,attempts=2,sleep=lambda _:None)
            self.assertEqual(len(dumps),2)

if __name__=='__main__':unittest.main()
