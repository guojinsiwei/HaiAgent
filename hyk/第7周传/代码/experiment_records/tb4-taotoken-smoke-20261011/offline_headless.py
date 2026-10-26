"""Exercise actual headless CLI and native bash with a local fake Messages server.
No external model calls. Workspace is separate from the benchmark task.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

observed = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        observed.append(request)
        if len(observed) > 8:
            self.send_error(429)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        def event(kind, **data):
            self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(dict(type=kind, **data)) + '\n\n').encode())
        event('message_start', message=dict(id='offline-'+str(len(observed)), type='message', role='assistant',
              model='deepseek-flash', content=[], usage=dict(input_tokens=100, output_tokens=0)))
        if len(observed) == 1:
            event('content_block_start', index=0, content_block=dict(type='tool_use', id='offline-tool-1', name='bash', input={}))
            event('content_block_delta', index=0, delta=dict(type='input_json_delta', partial_json=json.dumps({'command': "printf 'TB4_CHAIN_SMOKE_OK\\n'", 'description': 'Verify native bash transport'})))
            reason='tool_use'
        else:
            event('content_block_start', index=0, content_block=dict(type='text', text=''))
            event('content_block_delta', index=0, delta=dict(type='text_delta', text='Offline chain checked.'))
            reason='end_turn'
        event('content_block_stop', index=0)
        event('message_delta', delta=dict(stop_reason=reason, stop_sequence=None), usage=dict(output_tokens=20))
        event('message_stop')

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
root=Path('/opt/kz')
patch=root/'mock.patch.yml'
patch.write_text((root/'route.patch.yml').read_text().split('- id: llm-deepseek-account')[0]
    .replace('https://api.taotoken.net/token', 'http://127.0.0.1:' + str(server.server_port)))
wire_audit='--wire-audit' in sys.argv
suffix='-wire' if wire_audit else ''
work=Path('/tmp/kz-offline-work'+suffix)
work.mkdir(exist_ok=True)
env=dict(os.environ, PATH='/opt/node/bin:'+os.environ.get('PATH',''),
    DSH_HOME='/tmp/kz-offline-home'+suffix, KZ_WORKSPACE=str(work), KZ_AUDIT_DIR='/tmp/kz-offline-audit'+suffix,
    TAOTOKEN_API_KEY='offline-dummy-not-a-real-key', DSH_PERMISSION_MODE='danger-full-access')
node_args=['/opt/node/bin/node']
if wire_audit:
    env.update(DSH_EXPECT_ENDPOINT='http://127.0.0.1:'+str(server.server_port)+'/v1/messages',
        DSH_ROUTE_AUDIT='/logs/agent/offline-wire-audit.jsonl',DSH_WIRE_REQUEST_LIMIT='8')
    node_args += ['--import','/opt/kz/route-audit.mjs']
cmd=node_args+[str(root/'node_modules/@deepseek-ai/dsh/lib/bin.js'), '--profile', 'headless']
for p in ['config/common.patch.yml','route.patch.yml','.runtime/kz.patch.yml','mock.patch.yml']:
    cmd += ['--patch', str(root/p)]
cmd += ['--json','Run the bash command that prints TB4_CHAIN_SMOKE_OK and finish.']
result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,timeout=90)
server.shutdown()
Path('/logs/agent/offline-headless'+suffix+'.stdout').write_bytes(result.stdout)
Path('/logs/agent/offline-headless'+suffix+'.stderr').write_bytes(result.stderr)
seen_result=any('TB4_CHAIN_SMOKE_OK' in json.dumps(m) and m.get('role')=='user'
    and 'tool_result' in json.dumps(m) for r in observed for m in r.get('messages',[]))
checks=dict(exit_code=result.returncode, calls=len(observed), native_tool_result=seen_result,
    settings_ok=bool(observed) and all(r.get('max_tokens')==8192 and r.get('temperature')==0
        and r.get('thinking',{}).get('type')=='disabled' for r in observed))
checks['request_settings']=[{k:r.get(k) for k in ('model','max_tokens','temperature','thinking')} for r in observed]
checks['kz_tool_present']=any(t.get('name')=='kz_strategy' for r in observed for t in r.get('tools',[]))
if wire_audit:
    records=[json.loads(x) for x in Path(env['DSH_ROUTE_AUDIT']).read_text().splitlines()]
    checks['wire_requests']=sum(x['event']=='request' for x in records)
    checks['wire_integrity']=all(x['endpointMatches'] and x['keyMatchesInput'] for x in records if x['event']=='request')
    assert checks['wire_requests']==len(observed) and checks['wire_integrity']
Path('/logs/agent/offline-checks'+suffix+'.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks))
if result.returncode or not seen_result or not checks['settings_ok'] or not checks['kz_tool_present']:
    print(result.stderr.decode(errors='replace')[-5000:])
    print(result.stdout.decode(errors='replace')[-3000:])
    raise SystemExit(1)
