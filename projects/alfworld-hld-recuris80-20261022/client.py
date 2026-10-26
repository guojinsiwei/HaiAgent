"""Public text-action interface; no task files, oracle state, reset or answer API."""
import argparse,json,sys,urllib.request,uuid

p=argparse.ArgumentParser(description='Act in the persistent ALFWorld environment')
p.add_argument('action',nargs='?')
p.add_argument('--observe',action='store_true')
p.add_argument('--assert-won',action='store_true')
a=p.parse_args()
if a.action and (a.observe or a.assert_won):p.error('Use one action or one observation flag')
url='http://world:8080';payload=None
if a.action:payload=json.dumps(dict(action=a.action,request_id=uuid.uuid4().hex)).encode()
request=urllib.request.Request(url+('/step' if payload else '/observe'),data=payload,
    headers={'Content-Type':'application/json'})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=30) as f:
        result=json.load(f)
except Exception as error:
    print('ALFWORLD_TRANSPORT_ERROR',type(error).__name__,file=sys.stderr);raise SystemExit(2)
print(json.dumps(result,ensure_ascii=False,indent=2))
if a.assert_won and not result['won']:raise SystemExit(1)
