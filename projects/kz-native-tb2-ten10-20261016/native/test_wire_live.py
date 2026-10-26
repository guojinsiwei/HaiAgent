"""Actual HTTP retry/accounting, restricted to container loopback."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import solve
import anthropic_bridge

class WireTests(unittest.TestCase):
    def test_missing_usage_is_unknown(self):
        value=anthropic_bridge.envelope_from(dict(content=[dict(type='text',text='{}')],stop_reason='end_turn'))
        self.assertIsNone(value['usage'])

    def test_actual_retry_and_all_roles_count(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if len(calls)==1:self.send_response(503);self.end_headers();return
                value=dict(model='fixture',stop_reason='end_turn',content=[dict(type='text',text='{"action":"submit","summary":"fixture"}')],usage=dict(input_tokens=10,cache_read_input_tokens=20,output_tokens=5))
                body=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d,patch.object(anthropic_bridge,'ENDPOINT',f'http://127.0.0.1:{server.server_port}'):
                audit=solve.WireAudit(Path(d)/'wire.jsonl',secrets=('fixture-not-a-real-key',))
                for role in ('action','advisor','monitor','critic'):
                    cfg=solve.RetracModelConfig(provider='deepseek',model_name='fixture',api_key='fixture-not-a-real-key',base_url='http://localhost',request_attempts=2,timeout_seconds=10,max_wall_time_seconds=20,stream_response=False,thinking_enabled=False,max_tokens=100)
                    wire=solve.SharedJSONWire(cfg,audit,role,transport=solve.CheckedTransport(audit,transport=anthropic_bridge.request))
                    self.assertEqual(wire.complete_json(system_prompt='Full fixture task.',user_prompt='Full fixture task.')['action'],'submit')
                    self.assertEqual(wire.usage_summary()['prompt_tokens'],30)
                state=json.loads((Path(d)/'wire-state.json').read_text())
                self.assertEqual(len(calls),5);self.assertEqual(state['requests'],5)
                self.assertEqual(state['http_status_counts'],{'503':1,'200':4})
                self.assertNotIn('fixture-not-a-real-key',(Path(d)/'wire.jsonl').read_text())
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main(verbosity=2)
