"""Three fresh LongCLI tasks, one pilot then two concurrent, native DSH+KZ.
No LLM-based monitoring, no mail, no automatic paid retry, no algorithm edits.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
from common import ROOT, save, sha, import_tree, export_tree
from dispatch_policy import dispatch_trials, terminal_fault

def docker(*args,check=True,timeout=120):
    p=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=timeout)
    if check and p.returncode: raise RuntimeError('Docker operation failed: '+p.stderr[-600:])
    return p

class Proxy:
    # Per-trial network, TLS CONNECT pass-through. No credentials or HTTP bodies.
    def __init__(self,gateway):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_CONNECT(self):
                if self.path!='api.taotoken.net:443':self.send_error(403);return
                try:up=socket.create_connection(('api.taotoken.net',443),timeout=20)
                except OSError:self.send_error(502);return
                with up:
                    self.send_response(200,'Connection Established');self.end_headers()
                    peers=(self.connection,up)
                    while True:
                        ready,_,_=select.select(peers,[],[],600)
                        if not ready:return
                        for source in ready:
                            data=source.recv(65536)
                            if not data:return
                            (up if source is self.connection else self.connection).sendall(data)
        self.server=ThreadingHTTPServer((gateway,0),Handler)
        self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url=f'http://{gateway}:{self.server.server_port}'
    def close(self):self.server.shutdown();self.server.server_close()

def lines(path):
    if not path.exists():return []
    rows=[]
    for s in path.read_text(errors='replace').splitlines():
        try:rows.append(json.loads(s))
        except ValueError:pass # An in-progress final line is retried on next heartbeat.
    return rows

def progress(directory):
    route=lines(directory/'audit/request-route.jsonl')
    events=[e for p in (directory/'audit/kz').glob('*.jsonl') for e in lines(p)]
    requests=[e for e in events if e.get('event')=='request_admitted']
    tools=[e for e in events if e.get('event')=='tool_admitted']
    protocol=lines(directory/'audit/transport.jsonl')
    return dict(api_attempts=sum(e.get('event')=='request_shape' for e in route),
        protocol_retries=sum(e.get('event')=='protocol/retry' for e in protocol),
        protocol_retry_exhausted=any(e.get('event')=='protocol/retry-exhausted' for e in protocol),
        http_errors=[e.get('status') for e in route if e.get('event')=='response' and e.get('status')!=200],
        transport_errors=sum(e.get('event')=='transport_error' for e in route),
        shared_requests=len(requests),tools=len(tools),
        last_log_mtime=max((p.stat().st_mtime for p in (directory/'audit').rglob('*.jsonl')),default=None),
        budget_exhausted=any(e.get('event')=='budget_exhausted' for e in events))

def grade_source(summary,directory):
    from college_grader import grade
    report=grade(summary['job'],directory/'final-source.tar.gz',summary['artifact']['sha256'])
    name=report['container']
    assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()==ROOT.name
    assert docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='false'
    docker('rm',name)
    report['grading_container_destroyed']=True
    save(ROOT/'grades'/summary['job']/'result.json',report)
    return report

def trial(row,key):
    job='kz--'+row['task'];directory=ROOT/'jobs'/job
    directory.mkdir(parents=True,exist_ok=False)
    assert sha(row['starter_path'])==row['starter_sha256']
    import_tree(row['starter_path'],directory/'workspace')
    for part in ('home','audit'):(directory/part).mkdir()
    (directory/'instruction.txt').write_text(row['instruction'])
    token=secrets.token_hex(6);name='kz-dsh3-'+token;net='kz-dsh3-net-'+token
    proxy=None;p=None;container_created=False;network_created=False
    summary=dict(job=job,task=row['task'],state='preparing',started=time.time(),container=name,
        fresh_container=True,cross_task_memory=False,source_version='KZ-DSH-0.2.7')
    try:
        docker('network','create','--internal','--label','experiment='+ROOT.name,net);network_created=True
        gateway=json.loads(docker('network','inspect',net).stdout)[0]['IPAM']['Config'][0]['Gateway']
        proxy=Proxy(gateway)
        mounts=[(directory/'workspace','/app',False),(directory/'home','/dsh-home',False),
            (directory/'audit','/audit',False),(ROOT/'runtime/kz','/opt/kz',True),
            (ROOT/'runtime/node','/opt/node',True),(ROOT/'empty-tests','/tests',True),
            (ROOT/'container_run.py','/opt/experiment/container_run.py',True),
            (directory/'instruction.txt','/opt/experiment/instruction.txt',True)]
        args=['create','-i','--name',name,'--label','experiment='+ROOT.name,
            '--user',f'{os.getuid()}:{os.getgid()}','--network',net,'--cpus','2','--memory','8g',
            '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
            '-e','HOME=/dsh-home','-e','PATH=/opt/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','-w','/app']
        for source,target,ro in mounts:args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
        args += [row['image_id'],'python3','/opt/experiment/container_run.py']
        docker(*args);container_created=True
        actual=json.loads(docker('inspect',name,'--format','{{json .Mounts}}').stdout)
        assert all(Path(m['Source']).resolve().is_relative_to(directory.resolve()) for m in actual if m['RW'])
        assert next(m for m in actual if m['Destination']=='/tests')['RW'] is False
        save(directory/'isolation.json',dict(mounts=actual,network_internal=True,task_image=row['image_id']))
        with (directory/'controller.log').open('xb') as out:
            p=subprocess.Popen(['docker','start','-ai',name],stdin=subprocess.PIPE,stdout=out,stderr=out)
            p.stdin.write((json.dumps({'key':key,'proxy':proxy.url})+'\n').encode());p.stdin.close()
            summary['state']='solving';solve_started=time.time()
            while p.poll() is None:
                summary.update(updated=time.time(),**progress(directory));save(directory/'health.json',summary)
                # Abort known credential/config failures immediately; no paid retries.
                if any(code in (400,401,403,404) for code in summary['http_errors']):
                    summary['engineering_fault']='provider_request_rejected';docker('stop','-t','3',name,check=False);break
                if time.time()-solve_started>7260:
                    summary['stop_reason']='wall_budget';docker('stop','-t','3',name,check=False);break
                time.sleep(10)
            p.wait(timeout=30)
        docker('stop','-t','3',name,check=False)
        assert docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='false'
        summary.update(exit_code=p.returncode,**progress(directory))
        if summary.get('budget_exhausted'):summary['stop_reason']='shared_budget'
        elif p.returncode==0:summary['stop_reason']='native_completed'
        elif summary.get('stop_reason')!='wall_budget':
            stderr_path=directory/'audit/dsh.stderr.log'
            # Only classify exact stable markers; don't copy raw response text.
            with stderr_path.open('rb') as stream:
                stream.seek(max(0,stderr_path.stat().st_size-16384))
                stderr=stream.read().decode('utf-8',errors='replace')
            summary['engineering_fault']=terminal_fault(p.returncode,stderr,summary.get('engineering_fault'),
                recovery_exhausted=summary.get('protocol_retry_exhausted',False))
        # Historical transient errors are counters, not a terminal failure if
        # the native request retry successfully recovered and DSH exited 0.
        summary['artifact']=export_tree(directory/'workspace',directory/'final-source.tar.gz',source_only=True)
        summary.update(state='grading',updated=time.time());save(directory/'health.json',summary)
        report=grade_source(summary,directory)
        summary.update(grading_state=report['grading_state'],score=report.get('f2p',{}).get('step_score'),
            official_success=report.get('official_success'),grade_path=str(ROOT/'grades'/job/'result.json'))
        if report['grading_state']!='complete':summary['engineering_fault']='grading_failed'
        summary['state']='needs_attention' if summary.get('engineering_fault') else 'graded'
    except Exception as error:
        summary.update(state='needs_attention',engineering_fault=type(error).__name__,error=str(error)[:600].replace(key,'[REDACTED]'))
    finally:
        if container_created:
            docker('stop','-t','3',name,check=False)
            # Only remove this exact randomly-named experiment-owned container.
            owner=docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}',check=False).stdout.strip()
            if owner==ROOT.name:docker('rm','-f',name,check=False)
        if proxy:proxy.close()
        if network_created:docker('network','rm',net,check=False)
        summary.update(ended=time.time(),updated=time.time())
        summary['container_destroyed']=docker('inspect',name,check=False).returncode!=0
        if not summary['container_destroyed']:summary.update(state='needs_attention',engineering_fault='cleanup_unconfirmed')
        save(directory/'summary.json',summary);save(directory/'health.json',summary)
    return summary

def validate():
    ready=json.loads((ROOT/'ready.json').read_text());assert ready['passed']
    for name,value in json.loads((ROOT/'manifest.json').read_text())['files'].items():
        assert sha(ROOT/name)==value,'Changed sealed deployment: '+name
    return json.loads((ROOT/'protocol.json').read_text())

def campaign(key):
    protocol=validate()
    def publish(value):
        save(ROOT/'health.json',dict(value,pid=os.getpid(),updated=time.time()))
    final=dispatch_trials(protocol['tasks'],lambda row:trial(row,key),publish,concurrency=2)
    final.update(updated=time.time())
    save(ROOT/'summary.json',final);save(ROOT/'health.json',final)

if __name__=='__main__':
    if '--supervise' in sys.argv:
        payload=json.loads(sys.stdin.readline(16384));campaign(payload.pop('key'))
    else:
        validate();bundle=json.loads(sys.stdin.readline(16384));key=bundle.get('key','')
        assert key and key.isascii() and not any(c.isspace() for c in key)
        with (ROOT/'launch-once.marker').open('x') as f:f.write('Three authorized tasks, no automatic restarts.\n')
        with (ROOT/'supervisor.log').open('ab',buffering=0) as log:
            p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
            p.stdin.write((json.dumps({'key':key})+'\n').encode());p.stdin.close()
        key='';bundle={}
        print(json.dumps({'started':True,'pid':p.pid,'campaign':ROOT.name,'tasks':3,'pilot_then_concurrency':2}))
