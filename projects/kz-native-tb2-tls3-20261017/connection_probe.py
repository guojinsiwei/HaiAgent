"""Unauthenticated TLS preflight; never sends a model request or API key."""
import json,shlex,contextlib,importlib.util,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROBE="""import json,ssl,urllib.request,urllib.error
ctx=ssl.create_default_context()
assert ctx.cert_store_stats()['x509_ca']>0,'No trusted CA certificates'
try:
 with urllib.request.urlopen(urllib.request.Request('https://api.taotoken.net/token/v1/messages',method='GET'),context=ctx,timeout=20) as r:status=r.status
except urllib.error.HTTPError as e:status=e.code
assert status in (200,400,401,403,404,405),status
print(json.dumps(dict(tls_verified=True,http_status=status,ca_count=ctx.cert_store_stats()['x509_ca'],model_calls=0)))
"""
async def probe(agent,env):
 spec=importlib.util.spec_from_file_location('tls_probe_proxy',ROOT/'dependencies/network_proxy.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 server=m.ThreadingHTTPServer((m.HOST,0),m.Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 try:
  proxy='http://%s:%d'%server.server_address
  command='SSL_CERT_FILE=/opt/kz-standalone/cacert.pem HTTPS_PROXY='+shlex.quote(proxy)+' /opt/kz-python/bin/python3 -c '+shlex.quote(PROBE)
  result=await agent.exec_as_agent(env,command,cwd=agent.cwd,timeout_sec=30)
  if result.return_code:raise RuntimeError('Keyless TLS preflight failed before paid request')
  receipt=json.loads(result.stdout.strip().splitlines()[-1]);assert receipt['tls_verified'] and receipt['model_calls']==0
  (agent.logs_dir/'tls-preflight.json').write_text(json.dumps(receipt))
 finally:server.shutdown();server.server_close();worker.join(timeout=5)
