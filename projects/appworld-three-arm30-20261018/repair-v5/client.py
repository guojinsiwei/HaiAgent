"""Execute cells; --file runs a workspace script inside the task interpreter."""
import argparse,json,sys,urllib.request
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--file')
p.add_argument('--read-only',action='store_true')
a=p.parse_args()
code=Path(a.file).read_text() if a.file else sys.stdin.read()
if not code.strip():raise SystemExit('Pass Python code on stdin or use --file. Variables persist across cells.')
q={'code':code,'read_only':a.read_only}
req=urllib.request.Request('http://world:8080/execute',data=json.dumps(q).encode(),headers={'Content-Type':'application/json'})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=90) as response:r=json.load(response)
except Exception as e:
    print('APPWORLD_TRANSPORT_ERROR:',type(e).__name__,str(e));raise SystemExit(2)
print(r.get('output',r.get('error','')))
print('APPWORLD_AUDIT '+json.dumps(r.get('guard',{}),sort_keys=True))
for event in r.get('guard_events',[]):print('APPWORLD_NOTICE '+json.dumps(event,sort_keys=True))
if r.get('error') or r.get('output','').startswith('Execution failed.'):raise SystemExit(1)
