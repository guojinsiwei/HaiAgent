"""Configured DSH -> real Bash -> native receipt, loopback-only in network=none."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,os,subprocess,threading
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(body)
  if len(requests)>3:self.send_error(429);return
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  def event(kind,**data):self.wfile.write(('event: '+kind+'\ndata: '+json.dumps(dict(type=kind,**data))+'\n\n').encode())
  event('message_start',message=dict(id='offline-'+str(len(requests)),type='message',role='assistant',model='deepseek-flash',content=[],usage=dict(input_tokens=100,output_tokens=0)))
  if len(requests)==1:
   event('content_block_start',index=0,content_block=dict(type='tool_use',id='offline-bash',name='bash',input={}))
   event('content_block_delta',index=0,delta=dict(type='input_json_delta',partial_json=json.dumps(dict(command="test -r INSTRUCTION.md && test ! -e /tests/run-tests.sh && printf 'KZ_V2_NATIVE_RECEIPT_OK\\n'",description='Read original task and validate native shell isolation'))))
   reason='tool_use'
  else:
   event('content_block_start',index=0,content_block=dict(type='text',text=''))
   event('content_block_delta',index=0,delta=dict(type='text_delta',text='Offline native execution acceptance complete.'));reason='end_turn'
  event('content_block_stop',index=0);event('message_delta',delta=dict(stop_reason=reason,stop_sequence=None),usage=dict(output_tokens=20));event('message_stop')
def main():
 root=Path('/opt/kz');logs=Path('/audit');server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 endpoint=f'http://127.0.0.1:{server.server_port}'
 route=logs/'mock-route.yml';route.write_text((root/'route.patch.yml').read_text().replace('https://api.taotoken.net/token',endpoint))
 patch=logs/'kz-offline.yml';patch.write_text((root/'.runtime/kz.patch.yml').read_text().replace('criticEnabled: true','criticEnabled: false').replace('monitorEnabled: true','monitorEnabled: false'))
 env=dict(os.environ,TAOTOKEN_API_KEY='offline-dummy',DSH_HOME='/audit/home',KZ_WORKSPACE='/app',KZ_AUDIT_DIR='/audit/kz',
  KZ_TASK_INSTRUCTION_PATH='INSTRUCTION.md',DSH_PERMISSION_MODE='danger-full-access',DSH_APPROVAL_POLICY='never',
  PAIRED_AUDIT_DIR='/audit',PAIRED_ARM='kz',DSH_EXPECT_ENDPOINT=endpoint+'/v1/messages',DSH_ROUTE_AUDIT='/audit/route.jsonl',
  KZ_TRANSPORT_AUDIT_PATH='/audit/transport.jsonl',DSH_TELEMETRY_DISABLED='1')
 for key in list(env):
  if key.startswith('CAMPAIGN_BUDGET_'):del env[key]
 command=['/opt/node/bin/node','--import','/opt/kz/provider-guard.mjs','--import','/opt/kz/route-audit.mjs',str(root/'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','headless']
 for p in [root/'config/common.patch.yml',route,root/'.runtime/transport.patch.yml',patch]:command+=['--patch',str(p)]
 command+=['--json','-']
 result=subprocess.run(command,input=b'Execute the offline native receipt check once, then finish.',cwd='/app',env=env,capture_output=True,timeout=90)
 server.shutdown();(logs/'stdout.jsonl').write_bytes(result.stdout);(logs/'stderr.log').write_bytes(result.stderr)
 receipt=any(m.get('role')=='user' and 'tool_result' in json.dumps(m) and 'KZ_V2_NATIVE_RECEIPT_OK' in json.dumps(m) for r in requests for m in r.get('messages',[]))
 settings=bool(requests) and all(r.get('max_tokens')==16384 and r.get('model')=='deepseek-flash' for r in requests)
 checks=dict(passed=result.returncode==0 and receipt and settings,exit_code=result.returncode,requests=len(requests),native_receipt=receipt,settings=settings,paid_calls=0,external_network='disabled',monitor_and_critic='disabled for shell acceptance only; covered by separate integration tests')
 (logs/'checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks));assert checks['passed']
if __name__=='__main__':main()
