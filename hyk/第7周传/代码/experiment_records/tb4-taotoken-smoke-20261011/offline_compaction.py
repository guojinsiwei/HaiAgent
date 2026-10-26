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
summary_calls=[]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        observed.append(request)
        is_summary='acting as a compaction engine' in json.dumps(request.get('messages',[])[-1:])
        if is_summary: summary_calls.append(request)
        if len(observed) > 8:
            self.send_error(429)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        def event(kind, **data):
            self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(dict(type=kind, **data)) + '\n\n').encode())
        event('message_start', message=dict(id='offline-'+str(len(observed)), type='message', role='assistant',
              model='deepseek-flash', content=[], usage=dict(input_tokens=70000 if len(observed)==1 else 100, output_tokens=0)))
        if len(observed) == 1:
            event('content_block_start', index=0, content_block=dict(type='tool_use', id='offline-tool-1', name='bash', input={}))
            event('content_block_delta', index=0, delta=dict(type='input_json_delta', partial_json=json.dumps({'command': "printf 'TB4_CHAIN_SMOKE_OK\\n'", 'description': 'Verify native bash transport'})))
            reason='tool_use'
        else:
            event('content_block_start', index=0, content_block=dict(type='text', text=''))
            response=('Checkpoint: task is to print the marker; bash returned the marker. '+('context '*100)) if is_summary and len(summary_calls)==1 else 'OK' if is_summary else 'Offline chain checked.'
            event('content_block_delta', index=0, delta=dict(type='text_delta', text=response))
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
# Test-only trigger threshold. Retain the production maxTokens=8192 cap.
(root/'compaction-force.patch.yml').write_text('- id: compaction-basic\n  config:\n    maxTokens: 8192\n    thresholdRatio: 0.02\n    retainTokens: 1\n')
wire_audit='--wire-audit' in sys.argv
suffix='-compaction'
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
for p in ['config/common.patch.yml','route.patch.yml','.runtime/kz.patch.yml','mock.patch.yml','compaction-force.patch.yml']:
    cmd += ['--patch', str(root/p)]
cmd += ['--json','-']
prompt='Run the bash command that prints TB4_CHAIN_SMOKE_OK and finish. Offline padding follows: '+('alpha beta gamma delta. '*10000)
result=subprocess.run(cmd,input=prompt.encode(),cwd=work,env=env,capture_output=True,timeout=90)
server.shutdown()
Path('/logs/agent/offline-headless'+suffix+'.stdout').write_bytes(result.stdout)
Path('/logs/agent/offline-headless'+suffix+'.stderr').write_bytes(result.stderr)
seen_result=any('TB4_CHAIN_SMOKE_OK' in json.dumps(m) and m.get('role')=='user'
    and 'tool_result' in json.dumps(m) for r in observed for m in r.get('messages',[]))
checks=dict(exit_code=result.returncode, calls=len(observed), native_tool_result=seen_result,
    settings_ok=bool(observed) and all(r.get('max_tokens')==8192 and (r.get('temperature')==0 or 'acting as a compaction engine' in json.dumps(r.get('messages',[])[-1:]))
        and r.get('thinking',{}).get('type')=='disabled' for r in observed))
checks['request_settings']=[{k:r.get(k) for k in ('model','max_tokens','temperature','thinking')} for r in observed]
checks['compaction_calls']=len(summary_calls)
checks['compaction_output_caps']=[r.get('max_tokens') for r in summary_calls]
audit=[json.loads(line) for p in Path(env['KZ_AUDIT_DIR']).glob('*.jsonl') for line in p.read_text().splitlines()]
checks['budget_accounted_requests']=sum(e.get('event')=='request_admitted' for e in audit)
checks['compaction_accounted']=any(e.get('event')=='request_admitted' and e.get('role')=='compaction' for e in audit)
session_files=list((Path(env['DSH_HOME'])/'sessions').rglob('session.v4.jsonl.zstd'))
decode="""import fs from 'node:fs';import{zstdDecompressSync as dec}from'node:zlib';let b=fs.readFileSync(process.argv[1]),parts=[];while(b.length){let r=dec(b,{info:true});parts.push(r.buffer);if(!r.engine.bytesWritten)throw Error('no progress');b=b.subarray(r.engine.bytesWritten);}let e=Buffer.concat(parts).toString().split('\\n').filter(Boolean).map(JSON.parse).filter(x=>x.type==='compaction/end');console.log(JSON.stringify({success:e.filter(x=>!x.data.error).length,errors:e.filter(x=>x.data.error).map(x=>x.data.error)}));"""
ends=[json.loads(subprocess.check_output(['/opt/node/bin/node','--input-type=module','-e',decode,str(p)])) for p in session_files]
checks['compaction_successes']=sum(e['success'] for e in ends)
checks['compaction_errors']=[err for e in ends for err in e['errors']]
checks['kz_tool_present']=any(t.get('name')=='kz_strategy' for r in observed for t in r.get('tools',[]))
if wire_audit:
    records=[json.loads(x) for x in Path(env['DSH_ROUTE_AUDIT']).read_text().splitlines()]
    checks['wire_requests']=sum(x['event']=='request' for x in records)
    checks['wire_integrity']=all(x['endpointMatches'] and x['keyMatchesInput'] for x in records if x['event']=='request')
    assert checks['wire_requests']==len(observed) and checks['wire_integrity']
Path('/logs/agent/offline-checks'+suffix+'.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks))
if not checks['compaction_successes'] or checks['compaction_errors'] or not summary_calls or not checks['compaction_accounted'] or checks['budget_accounted_requests']!=len(observed) or result.returncode or not seen_result or not checks['settings_ok'] or not checks['kz_tool_present']:
    print(result.stderr.decode(errors='replace')[-5000:])
    print(result.stdout.decode(errors='replace')[-3000:])
    raise SystemExit(1)
