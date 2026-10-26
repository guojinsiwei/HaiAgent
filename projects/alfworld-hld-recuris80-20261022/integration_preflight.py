"""Exercise both real algorithm entries with network disabled and no budget."""
from pathlib import Path
import json,sys,subprocess,secrets,threading


def inside():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            calls.append(self.path);body=b'{"error":"per_task_budget_exhausted"}'
            self.send_response(402);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    arm=sys.argv[2]
    payload=dict(key='offline-dummy',arm=arm,instruction='Use the public ALFWorld client to complete the simulated task.',
      proxy='http://127.0.0.1:1',no_proxy='localhost,127.0.0.1',attempt_id='entry-'+arm,
      spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://127.0.0.1:{server.server_port}',
        CAMPAIGN_BUDGET_TOKEN='offline',CAMPAIGN_BUDGET_JOB='entry-test',CAMPAIGN_BUDGET_ARM='dsh' if arm=='recuris' else 'kz'))
    p=subprocess.run(['/opt/node/bin/node','/opt/experiment/container-run.mjs'],input=json.dumps(payload),text=True,capture_output=True,timeout=120)
    Path('/audit/entry.log').write_text(p.stdout+p.stderr);server.shutdown()
    stop=json.loads(Path('/audit/budget-stop.json').read_text())
    assert calls==['/reserve'] and stop['reason']=='per_task_budget_exhausted',(calls,stop)
    print(json.dumps(dict(arm=arm,passed=True,external_network=False,paid_calls=0)))


def main():
    import runner
    R=runner.R;docker=runner.docker;checks=[]
    for arm in ['hld','recuris']:
        d=R/'acceptance'/('entry-'+arm);d.mkdir(parents=True,exist_ok=False)
        for n in ['workspace','home','audit']:(d/n).mkdir()
        name='alf-entry-'+secrets.token_hex(4)
        args=runner.solver_args(d,'none',name);args[0]='run';args.remove('-i');args=args[:-3]
        args+=['-v',str(R/'integration_preflight.py')+':/entry.py:ro','-v',str(R/'test_loop.mjs')+':/test_loop.mjs:ro',
          runner.read(R/'image.json')['image'],'sh','-c',
          '/opt/node/bin/node /test_loop.mjs && python /entry.py --inside '+arm]
        try:
            p=docker(*args,check=False,timeout=160);(d/'controller.log').write_text(p.stdout+p.stderr)
            assert p.returncode==0,'Entry failed: '+str(d)
            checks.append(dict(arm=arm,passed=True));print('ENTRY_PASS',arm,flush=True)
        finally:docker('rm','-f',name,check=False)
    row=runner.read(R/'manifest.json')['selected'][0]
    d=R/'acceptance/client';d.mkdir()
    for n in ['workspace','home','audit','world']:(d/n).mkdir()
    token=secrets.token_hex(4);net='alf-probe-net-'+token;world='alf-probe-world-'+token;solver='alf-probe-solver-'+token
    try:
        docker('network','create','--internal',net)
        docker(*runner.world_args(row,d,net,world));initial=runner.get_world(world);assert not initial['won']
        args=runner.solver_args(d,net,solver);args[0]='run';args.remove('-i');args=args[:-3]
        code="import subprocess,json; c=['python','/opt/experiment/client.py']; a=json.loads(subprocess.check_output(c+['--observe'])); assert a['steps']==0 and not a['won']; b=json.loads(subprocess.check_output(c+['look'])); assert b['steps']==1; assert subprocess.run(c+['--assert-won'],stdout=subprocess.DEVNULL).returncode==1; print('CLIENT_PASS')"
        args += [runner.read(R/'image.json')['image'],'python','-c',code]
        p=docker(*args,check=False,timeout=60);(d/'controller.log').write_text(p.stdout+p.stderr)
        assert p.returncode==0,'Client bridge failed'
        mounts=json.loads(docker('inspect',solver,'--format','{{json .Mounts}}').stdout)
        assert not any(Path(m['Source']).resolve().is_relative_to((R/'data').resolve()) for m in mounts)
        checks.append(dict(client=True,passed=True,hidden_data_mounted=False))
    finally:
        for n in [solver,world]:docker('rm','-f',n,check=False)
        docker('network','rm',net,check=False)
    runner.save(R/'integration-preflight.json',dict(passed=True,checks=checks,paid_calls=0))


if __name__=='__main__':
    if '--inside' in sys.argv:inside()
    else:main()
