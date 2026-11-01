import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retry_control',HERE/'run_raw_retry.py')
retry=importlib.util.module_from_spec(spec);spec.loader.exec_module(retry)

class RetryTests(unittest.TestCase):
    def test_retry_only_changes_attempt_identification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'resources-1.json').write_text(json.dumps(dict(cpu_slots=[[4,5],[6,7]])))
            original=dict(task=retry.TASK,wall_seconds=7200,test_seconds=300,index=0,instruction='fixed')
            with patch.object(retry,'ROOT',root):
                row=retry.retry_row(dict(tasks=[original,dict(task='other')]))
            for key,value in original.items():self.assertEqual(row[key],value)
            self.assertEqual(row['method'],'raw')
            self.assertEqual(row['cpu_affinity'],[4,5])
            self.assertEqual(row['retry_of'],'raw--'+retry.TASK)
            self.assertNotEqual(row['job'],row['retry_of'])

    def test_existing_retry_never_relaunched(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'marker.json';marker.write_text('{}')
            with patch.object(retry,'validate',return_value={}),patch.object(retry,'MARKER',marker):
                with self.assertRaisesRegex(AssertionError,'already registered'):retry.attach()

if __name__=='__main__':unittest.main()
