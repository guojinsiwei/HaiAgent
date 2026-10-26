import tempfile,unittest,json,hashlib
from pathlib import Path
from status import normalized
class Tests(unittest.TestCase):
 def test_correct_only_verified_available_misclassification(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);f=root/'jobs/one';(f/'live').mkdir(parents=True);(f/'grade').mkdir()
   patch=b'example patch';(f/'model.patch').write_bytes(patch)
   docs={'solver.json':{'exit_code':0,'patch_sha256':hashlib.sha256(patch).hexdigest()},'grade/result.json':{'engineering_clean':True,'reward':1},'live/agent-exit.json':{'exit_code':0,'timed_out':False,'arm':'hld','attempt_id':'a'*32},'live/provider-state.json':{'kind':'available'}}
   for p,v in docs.items():(f/p).write_text(json.dumps(v))
   h={'rows':{'one':{'arm':'hld','state':'engineering_failed','provider_kind':'available','solver_exit':0}}}
   self.assertEqual(normalized(root,h)['summary']['hld']['passed'],1)
   self.assertEqual(h['rows']['one']['state'],'engineering_failed')
   (f/'model.patch').write_bytes(b'changed')
   self.assertEqual(normalized(root,h)['summary']['hld']['passed'],0)
   (f/'model.patch').write_bytes(patch);(f/'live/provider-state.json').write_text('{"kind":"transport"}')
   self.assertEqual(normalized(root,h)['summary']['hld']['passed'],0)
if __name__=='__main__':unittest.main()
