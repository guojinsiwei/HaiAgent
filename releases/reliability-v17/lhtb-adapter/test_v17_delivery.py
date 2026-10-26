import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from bestfgs.environment import _tree_manifest, _manifest_fingerprint
from delivery import budget_candidate
from outcomes import classify


class DeadlineDeliveryTests(unittest.TestCase):
    def test_explicit_optional_output_deferral_is_not_transport_recovery(self):
        result={'exception_info':None,'process_exit_code':0,'verifier_result':{'rewards':{'reward':0}}}
        events=[{'event':'model_error','role':'memory','failure_kind':'model_output'},
                {'event':'memory_update_deferred','role':'memory'},
                {'event':'method_end','stop_reason':'tool_budget'}]
        self.assertTrue(classify(result,events)['infrastructure_ok'])
        events[0]['failure_kind']='transport'
        self.assertFalse(classify(result,events)['infrastructure_ok'])

    def test_expired_budget_delivers_owned_intact_snapshot_without_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ws=root/'candidate';ws.mkdir()
            (ws/'policy.py').write_text('def step(): return "SPOT"')
            manifest=_tree_manifest(ws)
            fingerprint=hashlib.sha256(json.dumps([_manifest_fingerprint(manifest),{}],sort_keys=True).encode()).hexdigest()
            snapshot=SimpleNamespace(location=str(ws),fingerprint=fingerprint)
            state=SimpleNamespace(initial=object(),snapshots={'id':{'snapshot':snapshot,'manifest':manifest,'external':{}}},deadline=0)
            checkpoint=root/'checkpoint.json'
            self.assertIs(budget_candidate(state,checkpoint),state.initial)
            payload={'best_workspace':str(ws),'best_snapshot_fingerprint':fingerprint}
            checkpoint.write_text(json.dumps(payload))
            self.assertIs(budget_candidate(state,checkpoint),snapshot)
            (ws/'policy.py').write_text('def step(): pass')
            with self.assertRaisesRegex(RuntimeError,'changed'):
                budget_candidate(state,checkpoint)

    def test_unowned_or_unbound_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'checkpoint.json'
            snapshot=SimpleNamespace(location='/owned',fingerprint='known')
            state=SimpleNamespace(initial=object(),snapshots={'id':{'snapshot':snapshot}})
            for location in ['/owned','/elsewhere']:
                path.write_text(json.dumps({'best_workspace':location}))
                with self.assertRaises(RuntimeError):
                    budget_candidate(state,path)
