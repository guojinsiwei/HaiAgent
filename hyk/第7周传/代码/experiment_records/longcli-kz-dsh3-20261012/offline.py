"""Real native DSH/compaction against a loopback mock, no provider requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

observed=[];summaries=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        observed.append(request)
        summary='acting as a compaction engine' in json.dumps(request.get('messages',[])[-1:])
        if summary:summaries.append(request)
        if len(observed)>8:self.send_error(429);return
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        def event(kind,**data):
            self.wfile.write(('event: '+kind+'\ndata: '+json.dumps(dict(type=kind,**data))+'\n\n').encode())
        event('message_start',message=dict(id='offline-'+str(len(observed)),type='message',role='assistant',
            model='deepseek-flash',content=[],usage=dict(input_tokens=70000 if len(observed)==1 else 100,output_tokens=0)))
        if len(observed)==1:
            event('content_block_start',index=0,content_block=dict(type='tool_use',id='offline-bash',name='bash',input={}))
            event('content_block_delta',index=0,delta=dict(type='input_json_delta',partial_json=json.dumps(dict(
                command="printf 'KZ_LONGCLI_OFFLINE_OK\\n'; test -w /dev/null; test ! -e /tests/run-tests.sh",description='Check shell and test isolation'))))
            reason='tool_use'
        else:
            event('content_block_start',index=0,content_block=dict(type='text',text=''))
            text=('Checkpoint. '+('context '*100)) if summary and len(summaries)==1 else 'OK'
            event('content_block_delta',index=0,delta=dict(type='text_delta',text=text));reason='end_turn'
        event('content_block_stop',index=0)
        event('message_delta',delta=dict(stop_reason=reason,stop_sequence=None),usage=dict(output_tokens=20))
        event('message_stop')

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    root=Path('/opt/kz');work=Path(tempfile.mkdtemp(prefix='kz-chain-'))
    patch=work/'mock.yml'
    patch.write_text((root/'route.patch.yml').read_text().split('- id: llm-deepseek-account')[0]
        .replace('https://api.taotoken.net/token',f'http://127.0.0.1:{server.server_port}'))
    force=work/'compact.yml'
    force.write_text('- id: compaction-basic\n  config:\n    maxTokens: 32768\n    thresholdRatio: 0.002\n    retainTokens: 1\n')
    logs=Path('/audit');env=dict(os.environ,PATH='/opt/node/bin:'+os.environ.get('PATH',''),
        DSH_HOME=str(logs/'home'),KZ_WORKSPACE=str(work),KZ_AUDIT_DIR=str(logs/'kz'),
        TAOTOKEN_API_KEY='offline-dummy-not-real',DSH_PERMISSION_MODE='danger-full-access',
        DSH_EXPECT_ENDPOINT=f'http://127.0.0.1:{server.server_port}/v1/messages',
        DSH_ROUTE_AUDIT=str(logs/'route.jsonl'),DSH_WIRE_REQUEST_LIMIT='8')
    cmd=['/opt/node/bin/node','--import','/opt/kz/route-audit.mjs',str(root/'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','headless']
    for p in [root/'config/common.patch.yml',root/'route.patch.yml',root/'.runtime/kz.patch.yml',patch,force]:cmd+=['--patch',str(p)]
    cmd+=['--json','-']
    result=subprocess.run(cmd,input=('Check shell once. '+('alpha beta gamma delta. '*10000)).encode(),cwd=work,env=env,capture_output=True,timeout=120)
    server.shutdown()
    (logs/'stdout.jsonl').write_bytes(result.stdout);(logs/'stderr.log').write_bytes(result.stderr)
    audit=[json.loads(s) for p in (logs/'kz').glob('*.jsonl') for s in p.read_text().splitlines()]
    receipt=any(m.get('role')=='user' and 'tool_result' in json.dumps(m) and 'KZ_LONGCLI_OFFLINE_OK' in json.dumps(m) for r in observed for m in r.get('messages',[]))
    decode="import fs from 'node:fs';import{zstdDecompressSync as dec}from'node:zlib';let b=fs.readFileSync(process.argv[1]),a=[];while(b.length){let r=dec(b,{info:true});a.push(r.buffer);if(!r.engine.bytesWritten)throw Error('no progress');b=b.subarray(r.engine.bytesWritten);}console.log(JSON.stringify(Buffer.concat(a).toString().split('\\n').filter(Boolean).map(JSON.parse).filter(e=>e.type==='compaction/end').map(e=>e.data)));"
    ends=[e for p in (logs/'home/sessions').rglob('session.v4.jsonl.zstd') for e in json.loads(subprocess.check_output(['/opt/node/bin/node','--input-type=module','-e',decode,str(p)]))]
    checks=dict(exit_code=result.returncode,requests=len(observed),real_bash_receipt=receipt,
        settings=all(r.get('max_tokens')==32768 and r.get('thinking',{}).get('type')=='disabled' and (r.get('temperature')==0 or 'acting as a compaction engine' in json.dumps(r.get('messages',[])[-1:])) for r in observed),
        compaction_successes=sum(not e.get('error') for e in ends),compaction_errors=[e.get('error') for e in ends if e.get('error')],
        request_accounting=sum(e.get('event')=='request_admitted' for e in audit)==len(observed),
        compaction_accounting=any(e.get('event')=='request_admitted' and e.get('role')=='compaction' for e in audit),
        kz_tool_present=any(t.get('name')=='kz_update' for r in observed for t in r.get('tools',[])),paid_requests=0)
    checks['passed']=result.returncode==0 and receipt and all(checks[k] for k in ('settings','request_accounting','compaction_accounting','kz_tool_present','compaction_successes')) and not checks['compaction_errors']
    (logs/'checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks))
    raise SystemExit(0 if checks['passed'] else 1)

if __name__=='__main__':main()
