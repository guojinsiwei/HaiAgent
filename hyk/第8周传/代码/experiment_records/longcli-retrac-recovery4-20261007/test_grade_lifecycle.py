import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import grade_one
import grading_adapter


class GradeLifecycleTests(unittest.TestCase):
    def run_case(self, startup_failure=False, cleanup_failure=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);incoming=root/'incoming/retrac--task';incoming.mkdir(parents=True)
            (root/'protocol.json').write_text(json.dumps({'methods':['retrac'],'tasks':[{'task':'task'}],'experiment':'owned'}))
            (incoming/'summary.json').write_text('{"artifact":{"sha256":"hash"}}')
            (incoming/'final-source.tar.gz').write_bytes(b'artifact')
            def grade(*a):
                if startup_failure:raise TimeoutError('create uncertain')
                return {'container':'owned-container','grading_state':'complete','f2p':{'step_score':.5}}
            grader=types.SimpleNamespace(grade=grade)
            verbs=[]
            def docker(*args,**kw):
                verbs.append(args[0])
                if args[0]=='inspect':
                    return types.SimpleNamespace(returncode=0,stdout='{"experiment":"owned"}' if 'Labels' in args[-1] else 'false',stderr='')
                if cleanup_failure:raise TimeoutError('cleanup timeout')
                return types.SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch.object(grade_one,'ROOT',root),patch.object(grade_one,'sha',return_value='hash'),\
                 patch.dict('sys.modules',{'college_grader':grader}),\
                 patch.object(grading_adapter,'install',return_value={'owned':['owned-container'],'errors':[]}),\
                 patch.object(grading_adapter,'cleanup_docker',side_effect=docker):
                grade_one._grade_job('retrac--task')
            return json.loads((root/'grades/retrac--task/result.json').read_text()),verbs

    def test_startup_timeout_still_cleans_owned_container(self):
        result,verbs=self.run_case(startup_failure=True)
        self.assertEqual(result['grading_state'],'failed')
        self.assertEqual(result['error_type'],'TimeoutError')
        self.assertIn('rm',verbs)

    def test_score_survives_cleanup_failure(self):
        result,_=self.run_case(cleanup_failure=True)
        self.assertEqual(result['grading_state'],'complete')
        self.assertEqual(result['f2p']['step_score'],.5)
        self.assertFalse(result['grading_container_destroyed'])
        self.assertTrue(result['grading_cleanup_errors'])

    def test_normal_score_retained(self):
        result,_=self.run_case()
        self.assertTrue(result['grading_container_destroyed'])


if __name__=='__main__':unittest.main()
