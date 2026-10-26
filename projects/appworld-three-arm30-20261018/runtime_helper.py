"""Paired old/new KZDSH, six fresh LongCLI tasks, two independent solver slots."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import select
import socket
import subprocess
import sys
import threading
import time
from common import ROOT, save, sha, import_tree, export_tree
from spending import Ledger,server_for
GRADE_LOCK=threading.Lock()
TB=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')

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
    route=lines(directory/'audit/route.jsonl')
    events=[e for p in (directory/'audit/kz').glob('*.jsonl') for e in lines(p)]
    requests=[e for e in events if e.get('event')=='request_admitted']
    tools=[e for e in events if e.get('event')=='tool_admitted']
    def read(name):
        try:return json.loads((directory/'audit'/name).read_text())
        except (FileNotFoundError,ValueError):return {}
    shared=read('shared-state.json');budget=read('budget-stop.json');limit=read('limit-stop.json');provider=read('provider-stop.json')
    budget_reason=budget.get('reason') or limit.get('reason')
    valid_limit=budget_reason in ('per_task_budget_exhausted','campaign_budget_exhausted','per_task_request_limit','per_task_tool_limit')
    return dict(api_attempts=sum(e.get('event')=='request_shape' for e in route),
        http_errors=[e.get('status') for e in route if e.get('event')=='response' and e.get('status')!=200],
        transport_errors=sum(e.get('event')=='transport_error' for e in route),
        shared_requests=shared.get('requests',len(requests)),tools=shared.get('tools',len(tools)),
        budget_reason=budget_reason,provider_stop=provider,wall_stop=read('wall-limit.json'),
        last_log_mtime=max((p.stat().st_mtime for p in (directory/'audit').rglob('*.jsonl')),default=None),
        budget_exhausted=valid_limit or any(e.get('event')=='budget_exhausted' for e in events))

def grade_source(summary,directory):
    import college_grader
    from grading_environment import install
    install(college_grader,ROOT.name)
    from college_grader import grade
    report=grade(summary['job'],directory/'final-source.tar.gz',summary['artifact']['sha256'])
    name=report['container']
    assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()==ROOT.name
    assert docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='false'
    docker('rm',name)
    report['grading_container_destroyed']=True
    save(ROOT/'grades'/summary['job']/'result.json',report)
    return report

def trial(row,key,arm,ledger):
    job=arm+'--'+row['task'];directory=ROOT/'jobs'/job
    directory.mkdir(parents=True,exist_ok=False)
    assert sha(row['starter_path'])==row['starter_sha256']
    import_tree(row['starter_path'],directory/'workspace')
    for part in ('home','audit'):(directory/part).mkdir()
    (directory/'instruction.txt').write_text(row['instruction'])
    token=secrets.token_hex(6);name='kz-dsh3-'+token;net='kz-dsh3-net-'+token
    proxy=None;p=None;budget_server=None;container_created=False;network_created=False
    summary=dict(job=job,task=row['task'],state='preparing',started=time.time(),container=name,
        fresh_container=True,cross_task_memory=False,source_version=arm,arm=arm)
    try:
        docker('network','create','--internal','--label','experiment='+ROOT.name,net);network_created=True
        gateway=json.loads(docker('network','inspect',net).stdout)[0]['IPAM']['Config'][0]['Gateway']
        proxy=Proxy(gateway)
        budget_token=secrets.token_urlsafe(32)
        budget_server=server_for(ledger,budget_token,host=gateway,port=0)
        threading.Thread(target=budget_server.serve_forever,daemon=True).start()
        spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://{gateway}:{budget_server.server_port}',
            CAMPAIGN_BUDGET_TOKEN=budget_token,CAMPAIGN_BUDGET_JOB=job,CAMPAIGN_BUDGET_ARM='kz')
        mounts=[(directory/'workspace','/app',False),(directory/'home','/dsh-home',False),
            (directory/'audit','/audit',False),(ROOT/'runtime'/arm,'/opt/kz',True),
            (TB/'runtime/kz/node_modules','/opt/kz/node_modules',True),
            (TB/'runtime/node','/opt/node',True),(ROOT/'empty-tests','/tests',True),
            (ROOT/'container-run.mjs','/opt/experiment/container-run.mjs',True),
            (directory/'instruction.txt','/opt/experiment/instruction.txt',True)]
        args=['create','-i','--name',name,'--label','experiment='+ROOT.name,
            '--user',f'{os.getuid()}:{os.getgid()}','--network',net,'--cpus','2','--memory','8g',
            '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
            '-e','HOME=/dsh-home','-e','PATH=/opt/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','-w','/app']
        for source,target,ro in mounts:args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
        args += [row['image_id'],'/opt/node/bin/node','/opt/experiment/container-run.mjs']
        docker(*args);container_created=True
        actual=json.loads(docker('inspect',name,'--format','{{json .Mounts}}').stdout)
        assert all(Path(m['Source']).resolve().is_relative_to(directory.resolve()) for m in actual if m['RW'])
        assert next(m for m in actual if m['Destination']=='/tests')['RW'] is False
        save(directory/'isolation.json',dict(mounts=actual,network_internal=True,task_image=row['image_id']))
        with (directory/'controller.log').open('xb') as out:
            p=subprocess.Popen(['docker','start','-ai',name],stdin=subprocess.PIPE,stdout=out,stderr=out)
            p.stdin.write((json.dumps({'key':key,'proxy':proxy.url,'no_proxy':gateway+',localhost,127.0.0.1','spending':spending,'arm':'kz','instruction':row['instruction'],'attempt_id':job})+'\n').encode());p.stdin.close()
            summary['state']='solving';solve_started=time.time()
            while p.poll() is None:
                summary.update(updated=time.time(),**progress(directory));save(directory/'health.json',summary)
                # Abort known credential/config failures immediately; no paid retries.
                if any(code in (400,401,403,404) for code in summary['http_errors']):
                    summary['engineering_fault']='provider_request_rejected';docker('stop','-t','3',name,check=False);break
                if time.time()-solve_started>2760:
                    summary['stop_reason']='wall_budget';docker('stop','-t','3',name,check=False);break
                time.sleep(10)
            p.wait(timeout=30)
        docker('stop','-t','3',name,check=False)
        assert docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='false'
        summary.update(exit_code=p.returncode,**progress(directory))
        if summary.get('budget_exhausted'):summary['stop_reason']=summary.get('budget_reason') or 'shared_budget'
        elif summary.get('wall_stop'):summary['stop_reason']='wall_budget'
        elif p.returncode==0:summary['stop_reason']='native_completed'
        elif summary.get('stop_reason')!='wall_budget':summary['engineering_fault']=summary.get('engineering_fault','native_error_inspect_logs')
        if summary.get('provider_stop') and not summary.get('budget_exhausted'):
            summary.setdefault('engineering_fault','provider_transport_or_http')
        summary['artifact']=export_tree(directory/'workspace',directory/'final-source.tar.gz',source_only=True)
        summary.update(state='grading',updated=time.time());save(directory/'health.json',summary)
        with GRADE_LOCK:report=grade_source(summary,directory)
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
        if budget_server:budget_server.shutdown();budget_server.server_close()
        if network_created:docker('network','rm',net,check=False)
        summary.update(ended=time.time(),updated=time.time())
        summary['container_destroyed']=docker('inspect',name,check=False).returncode!=0
        if not summary['container_destroyed']:summary.update(state='needs_attention',engineering_fault='cleanup_unconfirmed')
        save(directory/'summary.json',summary);save(directory/'health.json',summary)
    return summary

def validate():
    ready=json.loads((ROOT/'ready.json').read_text());assert ready['passed']
    for name,value in ready['hashes'].items():assert sha(ROOT/name)==value,'Changed sealed deployment: '+name
    protocol=json.loads((ROOT/'protocol.json').read_text())
    assert len(protocol['tasks'])==6 and protocol['methods']==['baseline','candidate']
    return protocol

def campaign(key):
    protocol=validate();ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
    assert ledger.status()['settled_microcny']==0,'Fresh campaign only; no silent replay'
    queue=[]
    for i,row in enumerate(protocol['tasks']):
        for arm in (['baseline','candidate'] if i%2==0 else ['candidate','baseline']):queue.append((row,arm))
    results=[];active={}
    with ThreadPoolExecutor(max_workers=2) as pool:
        while queue or active:
            for future in list(active):
                if future.done():
                    row,arm=active.pop(future)
                    try:results.append(future.result())
                    except Exception as exc:results.append(dict(task=row['task'],arm=arm,state='needs_attention',engineering_fault=type(exc).__name__))
            # Reserve a conservative workspace allowance before admitting any new task.
            # Never clean other containers or reclaim historical snapshots.
            while queue and len(active)<2 and shutil.disk_usage('/var/lib/docker').free>40*2**30 and shutil.disk_usage(ROOT).free>10*2**30:
                row,arm=queue.pop(0);active[pool.submit(trial,row,key,arm,ledger)]=(row,arm)
            snapshot=dict(state='running' if active else 'waiting_for_storage' if queue else 'complete',updated=time.time(),pid=os.getpid(),
                concurrency=len(active),completed=results,pending=[dict(task=r['task'],arm=a) for r,a in queue],
                active=[dict(task=r['task'],arm=a) for r,a in active.values()],budget=ledger.status())
            save(ROOT/'health.json',snapshot)
            if queue or active:time.sleep(5)
    snapshot['state']='complete_with_engineering_failures' if any(r['state']!='graded' for r in results) else 'complete'
    save(ROOT/'summary.json',snapshot);save(ROOT/'health.json',snapshot)

if __name__=='__main__':
    if '--supervise' in sys.argv:
        payload=json.loads(sys.stdin.readline(16384));campaign(payload.pop('key'))
    elif '--launch' in sys.argv:
        validate();bundle=json.loads(sys.stdin.readline(16384));key=bundle.get('key','')
        assert key and key.isascii() and not any(c.isspace() for c in key)
        with (ROOT/'launch-once.marker').open('x') as f:f.write('Six paired KZDSH tasks, independent 48 CNY planned within 96 CNY authorization; no automatic replay.\n')
        with (ROOT/'supervisor.log').open('ab',buffering=0) as log:
            p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
            p.stdin.write((json.dumps({'key':key})+'\n').encode());p.stdin.close()
        key='';bundle={};time.sleep(2)
        assert p.poll() is None,'Supervisor exited; inspect before retry'
        print(json.dumps(dict(started=True,pid=p.pid,campaign=ROOT.name,trials=12,concurrency=2,maximum_cny=48)))
    else:validate();print('READY; no model calls')
