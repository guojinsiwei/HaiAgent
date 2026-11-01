"""One bad artifact must not prevent the next artifact's official grading."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import grading_worker as grader


class GradingIsolationTests(unittest.TestCase):
    def test_single_grade_failure_continues_healthy_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('jobs','grades','incoming'):(root/name).mkdir()
            for job in ('a-bad','b-good'):
                d=root/'jobs'/job;d.mkdir();(d/'final-source.tar.gz').write_bytes(b'fixture')
                grader.save(d/'summary.json',dict(state='awaiting_grade',artifact={'sha256':grader.sha(d/'final-source.tar.gz')}))
            grader.save(root/'health.json',dict(state='generation_complete',active=[]))
            calls=[]
            def grade(argv,**kwargs):
                job=argv[-1];calls.append(job)
                if job=='a-bad':raise RuntimeError('fixture bad grade')
                grader.save(root/'grades'/job/'result.json',dict(grading_state='complete',grading_container_destroyed=True))
                return SimpleNamespace(returncode=0)
            with patch.object(grader,'ROOT',root),patch.object(grader.subprocess,'run',side_effect=grade):
                grader.main()
            self.assertEqual(calls,['a-bad','b-good'])
            health=json.loads((root/'grading-health.json').read_text())
            self.assertEqual(health['scored'],1)
            self.assertEqual(list(health['errors']),['a-bad'])
