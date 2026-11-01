import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import grading_worker
from common import sha,save


class FreshGradingTests(unittest.TestCase):
    def test_first_artifact_creates_incoming_parents_and_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(grading_worker,'ROOT',Path(tmp)):
            root=Path(tmp);source=root/'jobs/retrac--test';source.mkdir(parents=True)
            (source/'final-source.tar.gz').write_bytes(b'frozen')
            summary={'state':'awaiting_grade','artifact':{'sha256':sha(source/'final-source.tar.gz')}}
            def launch(*args,**kwargs):
                self.assertTrue((root/'incoming/retrac--test/summary.json').exists())
                save(root/'grades/retrac--test/result.json',{'grading_state':'complete'})
                return types.SimpleNamespace(returncode=0)
            self.assertFalse((root/'incoming').exists())
            with patch.object(grading_worker.subprocess,'run',side_effect=launch):
                grading_worker.dispatch('retrac--test',source,summary)
            self.assertTrue((root/'incoming/retrac--test/final-source.tar.gz').exists())


if __name__=='__main__':unittest.main()
