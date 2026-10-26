import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import durable

class Durability(unittest.TestCase):
    def test_no_replay_when_child_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); ledger=root/'ledger'; ledger.mkdir()
            (root/'prior-results.json').write_text('[]')
            d=ledger/'raw-x'; d.mkdir()
            (d/'intent.json').write_text(json.dumps({'created':0,'task':{'task':'x'},'method':'raw'}))
            with patch.object(durable,'HERE',root),patch.object(durable,'LEDGER',ledger):
                rows,active,errors=durable.collect()
            self.assertEqual(rows,[]); self.assertEqual(active,[])
            self.assertIn('no_automatic_replay',errors[0]['reasons'][0])
    def test_reattach_and_harvest_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); ledger=root/'ledger'; ledger.mkdir()
            (root/'prior-results.json').write_text('[]')
            d=ledger/'raw-x'; d.mkdir()
            (d/'intent.json').write_text(json.dumps({'created':0,'task':{'task':'x'},'method':'raw'}))
            (d/'started.json').write_text(json.dumps({'pid':123,'identity':'abc'}))
            with patch.object(durable,'HERE',root),patch.object(durable,'LEDGER',ledger),patch.object(durable,'identity',return_value='abc'):
                self.assertEqual(len(durable.collect()[1]),1)
                (d/'result.json').write_text(json.dumps({'classification':{'infrastructure_ok':True}}))
                for _ in range(2):
                    rows,active,errors=durable.collect()
                    self.assertEqual(len(rows),1); self.assertEqual(active,[]); self.assertEqual(errors,[])

if __name__=='__main__': unittest.main()
