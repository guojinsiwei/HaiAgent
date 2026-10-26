import io
import json
from pathlib import Path
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import patch
import solve
import anthropic_bridge as bridge
from provider_policy import ProviderGate, ProviderQuotaUnavailable, classify
from bestfgs.models import ModelCallError
from native_repair import RepairRunner

class ProviderTests(unittest.TestCase):
    def test_quota_and_rate_limit_are_different(self):
        self.assertEqual(classify(429,'{"error":{"code":"QUOTA"}}'),'quota')
        self.assertEqual(classify(429,'{"error":{"type":"rate_limit_error"}}'),'temporary')
        self.assertEqual(classify(200,'{"error":{"code":"INSUFFICIENT_QUOTA"}}'),'quota')

    def test_gate_stops_all_later_requests_without_erasing_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            g=ProviderGate(d);g.response(429,'{"error":{"code":"QUOTA","message":"private fixture"}}')
            for _ in range(10):
                with self.assertRaises(ProviderQuotaUnavailable):g.before(90)
            self.assertNotIn('private fixture',g.path.read_text())

    def test_backoff_grows_and_respects_retry_after(self):
        now=[100.0];sleeps=[]
        def sleep(seconds):sleeps.append(seconds);now[0]+=seconds
        g=ProviderGate(None,clock=lambda:now[0],sleeper=sleep)
        g.response(429);g.before(90);g.response(503);g.before(90)
        g.response(429,retry_after='45');g.before(90)
        self.assertEqual(sleeps,[5,10,45])
        g.response(200);self.assertEqual(g.read()['consecutive'],0)

    def test_quota_bridge_makes_one_http_attempt_for_repeated_calls(self):
        with tempfile.TemporaryDirectory() as d:
            audit=solve.WireAudit(Path(d)/'audit.jsonl')
            payload=dict(model='fixture',messages=[],max_tokens=100,temperature=0)
            def error(*args,**kwargs):
                raise urllib.error.HTTPError('http://fixture',429,'quota',{},io.BytesIO(b'{"error":{"code":"QUOTA"}}'))
            with patch('urllib.request.urlopen',side_effect=error) as http:
                for _ in range(5):self.assertEqual(bridge.request('',payload,'fixture',90,recorder=audit),('quota',429))
            self.assertEqual(http.call_count,1)
            events=[json.loads(x) for x in (Path(d)/'provider-events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(x['event']=='request' for x in events),1)

    def test_four_role_clients_share_unavailable_latch(self):
        with tempfile.TemporaryDirectory() as d:
            audit=solve.WireAudit(Path(d)/'audit.jsonl')
            def error(*args,**kwargs):
                raise urllib.error.HTTPError('http://fixture',429,'quota',{},io.BytesIO(b'{"error":{"code":"QUOTA"}}'))
            with patch('urllib.request.urlopen',side_effect=error) as http:
                for role in ('action','monitor','advisor','critic'):
                    cfg=solve.RetracModelConfig(model_name='fixture',api_key='fixture',base_url='http://fixture',request_attempts=2)
                    wire=solve.SharedJSONWire(cfg,audit,role,transport=bridge.request)
                    with self.assertRaises(ModelCallError):wire.complete_json(system_prompt='fixture',user_prompt='fixture')
                    self.assertEqual(wire.last_failure_detail,'provider_quota')
            self.assertEqual(http.call_count,1)

    def test_restore_frozen_before_any_file_move(self):
        with tempfile.TemporaryDirectory() as d:
            workspace=Path(d)/'workspace';workspace.mkdir();f=workspace/'a';f.write_text('unchanged')
            env=solve.InPlace(workspace,Path(d)/'state')
            with self.assertRaises(ValueError):env.restore({'id':'anything'})
            self.assertEqual(f.read_text(),'unchanged')

    def test_model_restore_rejected_then_ordinary_work_continues(self):
        from test_native_repair import Scripted
        with tempfile.TemporaryDirectory() as d:
            workspace=Path(d)/'workspace';workspace.mkdir()
            actor=Scripted([dict(action='restore',checkpoint_id='x',reason='fixture'),dict(action='run',argv=['python3','-c','print("OK")']),dict(action='submit',summary='complete')])
            engine=RepairRunner(solve.InPlace(workspace,Path(d)/'state'),actor,Scripted([]),solve.LeanConfig(max_turns=10,max_tools=10,wall_seconds=30),Path(d)/'trace',routing=solve.RoutingPolicy(critic=False))
            result=engine.run(solve.TaskSpec('fixture','Do public work.'))
            self.assertTrue(result['submitted'],result)
            self.assertEqual(result['tool_calls'],1)

if __name__=='__main__':unittest.main()
