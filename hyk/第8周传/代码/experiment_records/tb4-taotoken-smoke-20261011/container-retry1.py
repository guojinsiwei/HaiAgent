"""Live native DSH gate, then one clean task; the key remains in memory."""
import hashlib
import json
from pathlib import Path
import sys
from dsh_runtime import execute,json_lines

key=sys.stdin.buffer.readline(8192).decode().strip()
if not key or len(key)>8000 or not key.isascii() or any(c.isspace() for c in key):
    raise SystemExit('Invalid key input; no model requests sent')
def fingerprint():
    return {str(p.relative_to('/app')):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path('/app').rglob('*') if p.is_file()}
before=fingerprint()
work=Path('/tmp/kz-live-gate-work')
work.mkdir(exist_ok=False)
config=Path('/opt/kz/.runtime/live-gate.patch.yml')
source=Path('/opt/kz/.runtime/kz.patch.yml').read_text()
for old,new in [('maxRequests: 40','maxRequests: 8'),('maxTools: 80','maxTools: 8'),('wallSeconds: 1800','wallSeconds: 180')]:
    assert source.count(old)==1
    source=source.replace(old,new)
config.write_text(source)
prompt="""This is a transport smoke test, not a benchmark problem. Work only in the current directory.
Use a native bash tool call to run: printf 'TB4_DSH_LIVE_OK\\n'
After receiving its actual output, reply with TB4_DSH_LIVE_OK and finish.
Do not inspect /app, environment variables, credentials, other directories, network, or hidden tests.
No complex plan is needed. Critic may inspect the actual tool receipt to confirm this literal task.
"""
logs=Path('/logs/agent/live-gate')
code=execute(key,prompt,str(work),logs,str(config),8,200)
events=json_lines(logs/'dsh.jsonl')
wire=json_lines(logs/'request-route.jsonl')
receipts=[e for e in events if e.get('type')=='tool_result' and e.get('status')=='completed' and 'TB4_DSH_LIVE_OK' in json.dumps(e.get('result'))]
responses=[e for e in wire if e.get('event')=='response']
requests=[e for e in wire if e.get('event')=='request']
audit=[e for p in (logs/'kz-audit').glob('*.jsonl') for e in json_lines(p)]
admitted=sum(e.get('event')=='request_admitted' for e in audit)
checks=dict(exit_code=code,requests=len(requests),budget_accounted_requests=admitted,
    route_and_key_match=bool(requests) and all(e['endpointMatches'] and e['keyMatchesInput'] for e in requests),
    streaming_http_ok=bool(responses) and len(responses)==len(requests) and all(e['status']==200 and 'text/event-stream' in (e['content_type'] or '') for e in responses),
    native_tool_receipt=bool(receipts),task_workspace_unchanged=before==fingerprint(),
    final_reply_observed=any(e.get('type')=='final' and 'TB4_DSH_LIVE_OK' in e.get('text','') for e in events))
passed=code==0 and admitted==len(requests) and all(checks[k] for k in ['route_and_key_match','streaming_http_ok','native_tool_receipt','task_workspace_unchanged','final_reply_observed'])
checks['passed']=passed
Path('/logs/agent/live-gate-result.json').write_text(json.dumps(checks,indent=2))
if not passed:
    Path('/logs/agent/agent-exit.json').write_text(json.dumps({'exit_code':65,'phase':'live_gate','task_started':False}))
    print(json.dumps({'live_gate':checks,'benchmark_started':False}))
    raise SystemExit(65)
print(json.dumps({'live_gate':checks,'benchmark_started':True}),flush=True)
code=execute(key,Path('/opt/kz/instruction.txt').read_text(),'/app','/logs/agent/task-run',
    '/opt/kz/.runtime/kz.patch.yml',40,1900)
key=''
Path('/logs/agent/agent-exit.json').write_text(json.dumps({'exit_code':code,'phase':'benchmark','task_started':True}))
print(json.dumps({'agent_exit_code':code}))
raise SystemExit(code)
