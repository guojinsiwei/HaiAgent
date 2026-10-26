"""Exercise real CLI/HTTP/timeout/delivery against a LOOPBACK mock, never a provider."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import threading
import container_runner

calls=[]
class Mock(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path.endswith('/chat/completions')
        calls.append(request['model'])
        code=["raise SystemExit(1)","from pathlib import Path; Path('fixture-old').unlink(); Path('fixture-answer').write_text('ok')"]
        decision={'done':True} if len(calls)>2 else {'done':False,'commands':[{'argv':[sys.executable,'-c',code[len(calls)-1]],'description':'synthetic transport fixture'}]}
        body=json.dumps({'id':'fixture','choices':[{'message':{'role':'assistant','content':json.dumps(decision)},'finish_reason':'stop'}],
                         'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server=HTTPServer(('127.0.0.1',0),Mock)
threading.Thread(target=server.serve_forever,daemon=True).start()
path=Path('/installed-agent/input.json')
payload=json.loads(path.read_text())
payload['args'][payload['args'].index('--base-url')+1]='http://127.0.0.1:'+str(server.server_port)+'/v1'
path.write_text(json.dumps(payload))
Path('/app/fixture-old').write_text('old')
try:
    assert container_runner.main()==0
    result=json.loads(Path('/logs/agent/runtime/search_checkpoint.json').read_text())
    assert result['decision_turns']==3
    assert result['comparison_metrics']['interaction_rounds']==2
    assert result['comparison_metrics']['tool_calls']==2
    assert len(calls)==3
    assert result['blocking_memory_mode']==('off' if payload['method']=='raw' else 'control')
    assert Path('/app/fixture-answer').read_text()=='ok'
    assert not Path('/app/fixture-old').exists()
    print(json.dumps({'passed':True,'loopback_mock_requests':len(calls),'external_model_api_requests':0}))
finally: server.shutdown()
