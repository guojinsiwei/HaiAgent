"""One task per process/container. Only execution is exposed to the solver."""
import json,os,sys
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from appworld import AppWorld
task=sys.argv[1]
world=AppWorld(task_id=task,experiment_name='trial',load_ground_truth=False,
               max_interactions=600,max_api_calls_per_interaction=1000,timeout_seconds=60,
               random_seed=100,raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True)
assert world.task.ground_truth is None
world.execute('pass')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!='/health':self.send_error(404);return
        self.reply({'ready':True,'task':task,'ground_truth_loaded':False})
    def reply(self,value):
        raw=json.dumps(value,ensure_ascii=False,default=str).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if self.path!='/execute':self.send_error(404);return
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=262144:self.send_error(413);return
        q=json.loads(self.rfile.read(size));code=q.get('code')
        if not isinstance(code,str):self.send_error(400);return
        try:
            result=world.execute(code)
            self.reply({'output':result,'interactions':world.num_interactions})
        except Exception as e:
            self.reply({'error':type(e).__name__+': '+str(e),'interactions':world.num_interactions})
print('WORLD_READY',task,flush=True)
HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
