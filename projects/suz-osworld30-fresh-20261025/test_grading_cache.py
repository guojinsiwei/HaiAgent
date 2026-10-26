from pathlib import Path
import hashlib,json,tempfile,unittest
from grading_cache import prepare_cache,archive_cache

class CacheTests(unittest.TestCase):
    def test_same_task_arms_and_preflight_cannot_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);assets=root/'assets';task=assets/'T';task.mkdir(parents=True)
            fixture=task/'Gold.docx';fixture.write_bytes(b'gold')
            (task/'result.docx').write_bytes(b'old ambiguous result')
            manifest=[{'file':'assets/T/Gold.docx','sha256':hashlib.sha256(b'gold').hexdigest()}]
            (task/'download-manifest.json').write_text(json.dumps(manifest))
            caches=[prepare_cache(assets,root/name,'T') for name in ['baseline','suz','preflight']]
            for i,cache in enumerate(caches):
                self.assertFalse((cache/'T/result.docx').exists())
                (cache/'T/result.docx').write_bytes(str(i).encode())
            self.assertEqual([(c/'T/result.docx').read_bytes() for c in caches],[b'0',b'1',b'2'])
            (caches[0]/'T/Gold.docx').write_bytes(b'changed')
            self.assertEqual(fixture.read_bytes(),b'gold')
            self.assertEqual((caches[1]/'T/Gold.docx').read_bytes(),b'gold')
            self.assertTrue(archive_cache(caches[1],root/'manifest.json'))
            with self.assertRaises(FileExistsError):prepare_cache(assets,caches[1],'T')

    def test_changed_fixture_fails_before_vm_or_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task=root/'assets/T';task.mkdir(parents=True)
            (task/'Gold').write_bytes(b'bad')
            (task/'download-manifest.json').write_text(json.dumps([{'file':'assets/T/Gold','sha256':'000'}]))
            with self.assertRaisesRegex(ValueError,'checksum'):prepare_cache(root/'assets',root/'run','T')

if __name__=='__main__':unittest.main()
