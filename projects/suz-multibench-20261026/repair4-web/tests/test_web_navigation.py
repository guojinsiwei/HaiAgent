import sys,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harness'))
from web_navigation import grading_navigation

class NavigationTests(unittest.TestCase):
    def test_dom_ready_only_during_grading_and_explicit_wait_preserved(self):
        calls=[]
        def goto(url,**kwargs):calls.append((url,kwargs));return SimpleNamespace(status=200)
        page=SimpleNamespace(goto=goto)
        with tempfile.TemporaryDirectory() as d:
            with grading_navigation(page,Path(d)/'navigation.jsonl'):
                page.goto('http://site/a')
                page.goto('http://site/b',wait_until='load')
            self.assertIs(page.goto,goto)
            self.assertEqual(calls[0][1],{'wait_until':'domcontentloaded'})
            self.assertEqual(calls[1][1],{'wait_until':'load'})
    def test_failure_is_propagated_and_method_restored(self):
        def goto(*args,**kwargs):raise TimeoutError('DOM not ready')
        page=SimpleNamespace(goto=goto)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(TimeoutError):
                with grading_navigation(page,Path(d)/'navigation.jsonl'):page.goto('http://site/a')
            self.assertIs(page.goto,goto)

if __name__=='__main__':unittest.main()
