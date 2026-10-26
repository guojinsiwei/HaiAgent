import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import prepare_transport as p
class MigrationTests(unittest.TestCase):
 def test_live_parent_cannot_fork_ledger(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'new';base=Path(d)/'old';root.mkdir();base.mkdir()
   (base/'admissions.json').write_text(json.dumps(dict(state='running',active=[dict(job='old')],rows=[])))
   with patch.object(p,'ROOT',root),patch.object(p,'BASE',base),patch.object(p,'verify_parent'):
    with self.assertRaisesRegex(AssertionError,'Parent still active'):p.finalize()
   self.assertFalse((root/'spending.sqlite').exists())
if __name__=='__main__':unittest.main()
