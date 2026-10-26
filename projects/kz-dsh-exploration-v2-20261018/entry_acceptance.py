"""Exercise the exact launch wrapper and all guards, with network=none and a denied lease."""
import json, os, secrets, subprocess, sys, threading
from pathlib import Path

def inside():
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 calls=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   calls.append(dict(path=self.path,body=body))
   data=json.dumps(dict(error='per_task_budget_exhausted')).encode()
   self.send_response(402);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 bundle=dict(key='offline-dummy',arm='kz',instruction='Read INSTRUCTION.md and begin the task.',attempt_id='entry-acceptance',proxy='',no_proxy='localhost,127.0.0.1',
  spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://127.0.0.1:{server.server_port}',CAMPAIGN_BUDGET_TOKEN='offline-dummy',CAMPAIGN_BUDGET_JOB='entry-acceptance',CAMPAIGN_BUDGET_ARM='kz'))
 result=subprocess.run(['/opt/node/bin/node','/opt/experiment/container-run.mjs'],input=json.dumps(bundle),text=True,capture_output=True,cwd='/app',timeout=75)
 server.shutdown();audit=Path('/audit')
 (audit/'entry.stdout').write_text(result.stdout);(audit/'entry.stderr').write_text(result.stderr)
 stop=json.loads((audit/'budget-stop.json').read_text()) if (audit/'budget-stop.json').exists() else {}
 checks=dict(passed=len(calls)==1 and calls[0]['path']=='/reserve' and stop.get('reason')=='per_task_budget_exhausted',
  budget_reservations_attempted=len(calls),lease_denied=True,external_network='disabled',paid_calls=0,exit_code=result.returncode,
  real_entrypoint=True,all_runtime_guards=True,monitor_and_critic='unchanged')
 (audit/'checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks));assert checks['passed']

def main():
 from common import import_tree,save
 from runner import docker,TB
 root=Path(__file__).resolve().parent;protocol=json.loads((root/'protocol.json').read_text());checks=[]
 for family in ['make-pytest','c-env']:
  row=next(r for r in protocol['tasks'] if r['family']==family)
  for arm in protocol['methods']:
   d=root/'entry-acceptance'/(arm+'-'+family+'-'+secrets.token_hex(3));d.mkdir(parents=True)
   import_tree(row['starter_path'],d/'workspace');(d/'audit').mkdir();(d/'home').mkdir()
   name='kz-v2-entry-'+secrets.token_hex(6)
   args=['run','--name',name,'--label','experiment='+root.name,'--network','none','--cpus','2','--memory','4g','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
    '--user',f'{os.getuid()}:{os.getgid()}','-e','HOME=/dsh-home','-e','PATH=/opt/node/bin:/usr/local/bin:/usr/bin:/bin','-w','/app']
   for source,target,ro in [(d/'workspace','/app',False),(d/'audit','/audit',False),(d/'home','/dsh-home',False),(root/'runtime'/arm,'/opt/kz',True),
    (TB/'runtime/kz/node_modules','/opt/kz/node_modules',True),(TB/'runtime/node','/opt/node',True),(root/'empty-tests','/tests',True),
    (root/'container-run.mjs','/opt/experiment/container-run.mjs',True),(root/'entry_acceptance.py','/opt/entry_acceptance.py',True)]:
    args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
   try:
    result=docker(*args,row['image_id'],'python3','/opt/entry_acceptance.py','--inside',check=False,timeout=100)
    (d/'controller.log').write_text(result.stdout+result.stderr)
   finally:
    assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()==root.name
    docker('stop','-t','3',name,check=False);docker('rm',name)
   assert result.returncode==0,'Full entry acceptance failed: '+str(d)
   check=json.loads((d/'audit/checks.json').read_text());check.update(arm=arm,family=family);checks.append(check)
   print('ENTRY',arm,family,'PASS',flush=True)
 save(root/'entry-acceptance.json',dict(passed=len(checks)==4,checks=checks,paid_calls=0))

if __name__=='__main__':
 if '--inside' in sys.argv:inside()
 else:main()
