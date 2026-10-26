"""Send a Python cell on stdin to this task's isolated AppWorld interpreter."""
import json,os,sys,urllib.request
code=sys.stdin.read()
if not code.strip():raise SystemExit('Pass Python code on stdin. Variables persist across cells.')
req=urllib.request.Request('http://world:8080/execute',data=json.dumps({'code':code}).encode(),headers={'Content-Type':'application/json'})
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(req,timeout=90) as response:r=json.load(response)
except Exception as e:
    print('APPWORLD_TRANSPORT_ERROR:',type(e).__name__,str(e));raise SystemExit(2)
print(r.get('output',r.get('error','')))
if r.get('error') or r.get('output','').startswith('Execution failed.'):raise SystemExit(1)
