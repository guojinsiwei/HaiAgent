"""Full launch entry, actual plugins/worker, all model HTTP denied before transmission."""
from pathlib import Path
import json,os,secrets,subprocess,threading,sys
def inside():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            calls.append(self.path);raw=b'{"error":"per_task_budget_exhausted"}'
            self.send_response(402);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    arm=sys.argv[2]
    payload={'key':'offline-dummy','arm':arm,'instruction':'Read INSTRUCTION.md and solve the task.','proxy':'','no_proxy':'127.0.0.1,localhost',
      'spending':{'CAMPAIGN_BUDGET_REQUIRED':'1','CAMPAIGN_BUDGET_URL':f'http://127.0.0.1:{server.server_port}','CAMPAIGN_BUDGET_TOKEN':'offline-dummy','CAMPAIGN_BUDGET_JOB':'entry-acceptance','CAMPAIGN_BUDGET_ARM':'dsh' if arm=='dsh' else 'kz'}}
    p=subprocess.run(['/opt/node/bin/node','/opt/experiment/container-run.mjs'],input=json.dumps(payload),text=True,capture_output=True,timeout=90)
    server.shutdown()
    Path('/audit/entry.log').write_text(p.stdout+p.stderr)
    stop=json.loads(Path('/audit/budget-stop.json').read_text()) if Path('/audit/budget-stop.json').exists() else {}
    check={'arm':arm,'passed':calls==['/reserve'] and stop.get('reason')=='per_task_budget_exhausted','calls':calls,'external_network':False,'paid_calls':0}
    Path('/audit/entry-check.json').write_text(json.dumps(check));print(json.dumps(check));assert check['passed']
def main():
    from runner import R,V,read,save,docker,solver_args
    checks=[];image=read(R/'image.json')['image']
    for arm in ['hld','kzdsh-new']:
        d=V/'acceptance'/('entry-'+arm+'-'+secrets.token_hex(3));d.mkdir(parents=True)
        for part in ['workspace','home','audit']:(d/part).mkdir()
        (d/'workspace/INSTRUCTION.md').write_text('Read local task instructions and call the simulated application APIs.')
        name='aw-entry-'+secrets.token_hex(5)
        args=solver_args(d,'none',name,arm,image);args[0]='run';args.remove('-i');args=args[:-3]
        args+=['-v',str(V/'entry_acceptance.py')+':/entry_acceptance.py:ro',image,'python','/entry_acceptance.py','--inside',arm]
        try:
            p=docker(*args,check=False,timeout=110);(d/'controller.log').write_text(p.stdout+p.stderr)
        finally:docker('rm','-f',name,check=False)
        assert p.returncode==0,'Full entry failed: '+str(d)
        checks.append(read(d/'audit/entry-check.json'));print('ENTRY_PASS',arm,flush=True)
    save(V/'entry-acceptance.json',{'passed':all(r['passed'] for r in checks),'checks':checks,'paid_calls':0})
if __name__=='__main__':
    if '--inside' in sys.argv:inside()
    else:main()
