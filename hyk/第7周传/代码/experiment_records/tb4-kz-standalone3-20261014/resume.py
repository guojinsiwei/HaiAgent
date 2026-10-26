"""Independent queue: legacy KZ pilot + ONLY not-started original DSH tasks."""
import collections,datetime,fcntl,hashlib,importlib.util,json,os,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
sys.path.append(str(BASE))
import network_proxy
spec=importlib.util.spec_from_file_location('snapshot_helpers',BASE/'runner.py');helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers);helpers.ROOT=ROOT
read=helpers.read
def save(name,value):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2));t.replace(p)
def validate():
    r=read(ROOT/'ready.json');assert r.get('passed'),'Acceptance required'
    for n,h in r['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,'Source drift: '+n
    for n,h in read(BASE/'ready.json')['files'].items():assert hashlib.sha256((BASE/n).read_bytes()).hexdigest()==h,'Original DSH deployment drift: '+n
def rows_for_start():
    old=read(BASE/'admissions.json')['rows']
    rows=[dict(arm='legacy-kz',task=t,job='legacy-kz-'+t,state='pending') for t in ('payments-pipeline-fix','mvcc-lsm-compaction','uefi-bootkit')]
    rows += [dict(arm='dsh',task=r['task'],job='resume-'+r['job'],state='pending',original_job=r['job']) for r in old if r['arm']=='dsh' and r['state']=='pending']
    return rows
def command(row,offline=False):
    agent=('harbor_legacy:OfflineLegacy' if offline else 'harbor_legacy:LegacyAgent') if row['arm']=='legacy-kz' else ('harbor_pair:OfflineAgent' if offline else 'harbor_pair:PairAgent')
    return [PY,str(ROOT/'entry_harbor.py'),'run','-p',str(BASE/'official/tasks'/row['task']),'-a',agent,'--env','docker','--no-delete','-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1','--job-name',('preflight-' if offline else '')+row['job'],'-o',str(ROOT/('preflight' if offline else 'jobs'))]
def refresh(row):
    out=helpers.snapshot(row)
    if row['arm']=='legacy-kz' and out.get('trial'):
        d=Path(out['trial'])/'agent/live';p=read(d/'progress.json');out.update(requests=p.get('requests',0),tools=p.get('tools',0),last_progress=p.get('time'))
        wire=read(d/'wire-state.json');out.update(logical_requests=p.get('requests',0),requests=wire.get('requests',0),http_status_counts=wire.get('http_status_counts',{}))
        if wire.get('time'):out['last_progress']=datetime.datetime.fromtimestamp(wire['time'],datetime.timezone.utc).isoformat()
        if out['http_status_counts'].get('401'):out['auth_failure']='401'
        result=read(d/'result.json');out['legacy_stop_reason']=result.get('stop_reason')
    return out
def old_running():
    h=read(BASE/'health.json');return sum(x['arm']=='dsh' for x in h.get('running',[]))
def supervise():
    validate()
    with (ROOT/'supervisor.lock').open('a') as lock:
      fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      assert not (ROOT/'admissions.json').exists(),'No automatic paid replay'
      rows=rows_for_start();save('admissions.json',dict(rows=rows));active={};pause=False;controls=ROOT/'controls.json'
      proxy=network_proxy.ThreadingHTTPServer((network_proxy.HOST,28480),network_proxy.Handler)
      threading.Thread(target=proxy.serve_forever,daemon=True).start()
      env=dict(os.environ,PYTHONPATH=str(ROOT)+':'+str(BASE),PAIRED_PROXY_URL='http://10.123.0.1:28480')
      accepted=set((read(ROOT/'ready.json').get('legacy_tasks') or []))
      preflights={}
      try:
        while True:
          ctl=read(controls);stop=set(ctl.get('stop_dispatch_arms',[]))
          for job,(p,log,row,offline) in list(active.items()):
            if p.poll() is None:continue
            log.close();del active[job]
            if offline:
              results=list((ROOT/'preflight'/('preflight-'+row['job'])).glob('*/result.json'));result=read(results[0]) if len(results)==1 else {}
              if p.returncode==0 and result.get('verifier_result') and not result.get('exception_info'):accepted.add(row['task']);row['state']='pending'
              else:row.update(state='blocked_environment',exception=(result.get('exception_info') or {}).get('exception_type','preflight_failed'))
            else:
              row.update(refresh(row),harbor_exit=p.returncode)
              if row['state'] not in ('graded','engineering_failure'):row.update(state='engineering_failure',fault='missing_final_result')
              if row.get('auth_failure'):pause=True
              if row['arm']=='legacy-kz' and (row.get('fault') or row.get('legacy_stop_reason')=='infrastructure_error'):stop.add('legacy-kz');save('controls.json',dict(stop_dispatch_arms=sorted(stop),reason='pilot_engineering_fault'))
            save('admissions.json',dict(rows=rows))
          running=[refresh(v[2]) for v in active.values() if not v[3]]
          count=collections.Counter(r['arm'] for r in running);old=old_running()
          for row in rows:
            if pause or row['state']!='pending' or row['arm'] in stop:continue
            if row['arm']=='dsh' and count['dsh']+old>=2:continue
            if row['arm']=='legacy-kz' and count['legacy-kz']>=1:continue
            ready_old=read(BASE/'admissions.json').get('tasks',{}).get(row['task'],{}).get('state')=='ready'
            offline=row['task'] not in accepted and (row['arm']=='legacy-kz' or not ready_old)
            if offline and any(v[3] for v in active.values()):continue
            row.update(state='admitted',started=time.time());save('admissions.json',dict(rows=rows))
            log=(ROOT/(row['job']+('.preflight.log' if offline else '.log'))).open('xb')
            childenv=dict(env,PAIRED_TASK=row['task'])
            if offline:childenv.pop('TAOTOKEN_API_KEY',None)
            try:p=subprocess.Popen(command(row,offline),env=childenv,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            except Exception:log.close();row.update(state='launch_error');save('admissions.json',dict(rows=rows));continue
            row.update(state='preflighting' if offline else 'starting',pid=p.pid);active[row['job']]=(p,log,row,offline)
            if not offline:count[row['arm']]+=1
            save('admissions.json',dict(rows=rows))
          running=[refresh(v[2]) for v in active.values() if not v[3]]
          h=dict(state='paused' if pause else 'running',updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supervisor_pid=os.getpid(),planned=len(rows),finished=sum(r.get('grade') is not None for r in rows),pending=sum(r['state']=='pending' for r in rows),running=running,results=rows,old_dsh_running=old,stop_dispatch_arms=sorted(stop))
          if not active and not any(r['state']=='pending' and r['arm'] not in stop for r in rows):h['state']='finished_or_held'
          save('health.json',{k:v for k,v in h.items() if k!='results'});save('summary.json',h)
          if h['state']=='finished_or_held':break
          time.sleep(10)
      except BaseException as error:
        save('supervisor-error.json',dict(error_type=type(error).__name__,dispatch_stopped=True))
        # Keep task network service alive until admitted work has ended.
        while active:
          for job,(p,log,row,offline) in list(active.items()):
            if p.poll() is not None:
              log.close();del active[job]
              if not offline:row.update(refresh(row),harbor_exit=p.returncode)
          running=[refresh(v[2]) for v in active.values() if not v[3]]
          h=dict(state='dispatch_failed_draining',updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),running=running,results=rows)
          save('summary.json',h);save('health.json',{k:v for k,v in h.items() if k!='results'});save('admissions.json',dict(rows=rows))
          time.sleep(10)
        raise
      finally:proxy.shutdown()
def launch():
    validate();b=json.loads(sys.stdin.readline());key=b['key'];assert key
    with (ROOT/'launch-once.marker').open('x') as f:f.write(str(time.time()))
    with (ROOT/'supervisor.log').open('xb') as log:
      p=subprocess.Popen([PY,__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    time.sleep(2)
    if p.poll() is not None:raise RuntimeError('Supervisor failed before acknowledgement; inspect log before retry')
    print(json.dumps(dict(pid=p.pid,server_detached=True,legacy_tasks=3,dsh_mode='resume_only_pending',max_legacy=1,max_dsh_including_old=2)))
if __name__=='__main__':
    if '--launch' in sys.argv:launch()
    elif '--supervise' in sys.argv:supervise()
    else:validate();print('READY')
