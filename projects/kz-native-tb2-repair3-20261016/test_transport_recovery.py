import io,json,tempfile,threading,unittest,sys
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parent/'native'))
import anthropic_bridge as bridge
from spending_client import SpendingClient,SpendingStopped
from spending import Ledger
from provider_policy import ProviderGate

class RecoveryTests(unittest.TestCase):
    def test_unknown_failure_then_success_retains_cost_and_real_status(self):
        self.scenario([(502,{'error':{'message':'SECRET-body'}}),(200,{'content':[{'type':'text','text':'{}'}],'stop_reason':'end_turn','usage':{'input_tokens':10,'output_tokens':5}})],False)
    def test_two_unknown_responses_stop_without_faking_402(self):
        self.scenario([(502,{'error':{}}),(502,{'error':{}})],True)
    def scenario(self,responses,terminal):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                status,value=responses[len(seen)-1];data=json.dumps(value).encode()
                self.send_response(status);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);url=f'http://127.0.0.1:{server.server_port}'
                ledger=Ledger(root/'budget.sqlite',dict(campaign_limit_microcny=40000000,task_limit_microcny=4000000,input_ceiling_tokens=128000,max_output_tokens=16384,requests_per_task=120,jobs=['trial','next'],endpoint=url,model='fixture'))
                class Client:
                    def reserve(self,target,body,seconds):
                        id=str(len(seen));ledger.reserve(dict(id=id,job='trial',arm='native-kz',endpoint=target,model=body['model'],max_tokens=body['max_tokens']));return id
                    def settle(self,id,usage):
                        from spending_client import cost_usage
                        value=ledger.settle(dict(id=id,tokens=cost_usage(usage)))
                        if value.get('task_halt_reason'):raise SpendingStopped(value['task_halt_reason'])
                recorder=type('Recorder',(),{'path':root/'audit.jsonl'})()
                payload=dict(model='fixture',messages=[dict(role='user',content='fixture')],max_tokens=16384,temperature=0)
                with patch.object(bridge,'ENDPOINT',url),patch.object(bridge,'SpendingClient',Client),patch.object(ProviderGate,'before',lambda s,n:n):
                    self.assertEqual(bridge.request('',payload,'SECRET-key',5,recorder),('http',502))
                    result=bridge.request('',payload,'SECRET-key',5,recorder)
                self.assertEqual(result[0],'fatal' if terminal else 'ok')
                self.assertEqual(len(seen),2)
                self.assertEqual(ledger.status()['uncertain_microcny'],387072*(2 if terminal else 1))
                self.assertEqual(ledger.status()['settled_microcny'],0 if terminal else 60)
                text=(root/'provider-events.jsonl').read_text();self.assertIn('502',text);self.assertNotIn('SECRET',text)
                self.assertIsNone(ledger.status()['halt_reason'])
                ledger.reserve(dict(id='next',job='next',arm='native-kz',endpoint=url,model='fixture',max_tokens=16384))
                self.assertEqual((root/'budget-stop.json').exists(),terminal)
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
