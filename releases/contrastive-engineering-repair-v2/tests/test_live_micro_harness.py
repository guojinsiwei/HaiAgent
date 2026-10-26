import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'microtests'),str(ROOT/'sources/bestfgs-project/src')]
from live_fixture_tools import dispatch
from run_live_memory import MicroWorkspace, run_case


class FixtureToolTests(unittest.TestCase):
    def workspace(self,case):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        import shutil
        root = Path(temp.name)/'fixture'
        shutil.copytree(ROOT/'microtests/fixtures'/case,root)
        return root
    def test_cannot_write_checker_or_outside_fixture(self):
        root = self.workspace('path')
        for argv in (['write','read_value.py','bad'],['write','../escape','bad'],
                     ['read','../escape'],['copy','valid.txt','read_value.py'],['bash','-lc','true']):
            with self.subTest(argv=argv),self.assertRaises(ValueError): dispatch(root,'path',argv)
    def test_copy_repairs_the_only_declared_target(self):
        root = self.workspace('dependency')
        self.assertEqual(dispatch(root,'dependency',['copy','available/trap_dep.py','trap_dep.py']),0)
        self.assertEqual((root/'trap_dep.py').read_bytes(),(root/'available/trap_dep.py').read_bytes())
    def test_arbitrary_dependency_code_is_not_executed(self):
        root = self.workspace('dependency')
        (root/'trap_dep.py').write_text('raise AssertionError("must not run")',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'immutable module'): dispatch(root,'dependency',['check'])


@unittest.skipUnless(os.name=='posix','requires production Linux LiveWorkspace')
class LiveHarnessTests(unittest.TestCase):
    def test_all_three_grading_paths_with_mock_provider_no_api(self):
        for case in ('path','dependency','shape'):
            for enabled in (False,True):
                with self.subTest(case=case,memory_enabled=enabled),tempfile.TemporaryDirectory() as temp:
                    copies = dict(path=['valid.txt','missing.txt'],dependency=['available/trap_dep.py','trap_dep.py'],
                                  shape=['fixed.json','case.json'])
                    actions = [dict(action='run',argv=['microtool','copy',*copies[case]],purpose='fixture repair'),
                               dict(action='run',argv=['microtool','check'],purpose='fixture verification'),
                               dict(action='submit',summary='fixture delivery')]
                    if enabled:
                        actions = [dict(memory_review=dict(ids=['M1'],decision='different_route' if i==0 else 'recheck',
                            observed_result='The seeded check failed twice.',applicability='Recheck the current fixture state.',
                            reason='Test harness mock; not a real model decision.'),
                            strategy_adjustment='Apply the explicit mock fixture correction and check it.',**a) for i,a in enumerate(actions)]
                    class MockTransport:
                        def __init__(self,cfg): self.config=cfg;self.actions=iter(actions);self.request_audit=None
                        def complete_json(self,**kwargs): return next(self.actions)
                        def usage_summary(self): return dict(api_requests=0,api_responses=0)
                    with patch('run_live_memory.OpenAICompatibleJSONClient',MockTransport):
                        summary = run_case(case,enabled,'fixture-private-key',SimpleNamespace(model='mock-only'),
                            Path(temp)/'audit',lambda _:None)
                    self.assertTrue(summary['fixture_goal_verified'],summary)
                    self.assertTrue(summary['submitted'],summary)
                    self.assertEqual(summary['scripted_failure_seeds'],2)
                    self.assertEqual(summary['provider_decisions'],3)
                    self.assertEqual(summary['actual_api_usage']['api_requests'],0)
                    self.assertEqual(summary['repeat_proposals_refused'],0)
    def test_general_shell_is_not_executed(self):
        import time
        with tempfile.TemporaryDirectory() as temp:
            env=MicroWorkspace(ROOT/'microtests/fixtures/path',Path(temp)/'run','path')
            result=env.execute(dict(argv=['bash','-lc','touch escaped'],purpose='unsupported'),time.monotonic()+5)
            self.assertTrue(result.blocked)
            self.assertFalse((env.workspace/'escaped').exists())


if __name__=='__main__': unittest.main()
