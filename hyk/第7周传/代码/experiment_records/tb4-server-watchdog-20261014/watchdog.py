"""Server-only task deadline watcher. No model API, secrets, email or Codex timer."""
import argparse,concurrent.futures,datetime,fcntl,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CAMPAIGNS=[Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014'),Path('/var/tmp/lizh639-tb4-kz-standalone3-20261014')]
LIMIT=10800
INTERVAL=10
GRACE=15

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def save(name,value):
    p=ROOT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2));t.replace(p)

def command(args,**kwargs):
    r=subprocess.run(args,capture_output=True,text=True,timeout=kwargs.pop('timeout',20),**kwargs)
    if r.returncode:raise RuntimeError('command_failed:'+args[0]+':'+str(r.returncode))
    return r.stdout

def inventory():
    ids=command(['docker','ps','-q','--filter','label=com.docker.compose.service=main']).split()
    if not ids:return []
    # Intentionally never request Config.Env or full docker inspect.
    value=command(['docker','inspect','--format','{"id":{{json .Id}},"name":{{json .Name}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}},"running":{{json .State.Running}}}',*ids])
    return [json.loads(line) for line in value.splitlines()]

def matching_container(containers,trial):
    expected_project=trial.name.lower()+'__env'
    matches=[]
    for c in containers:
        labels=c.get('labels') or {}
        if labels.get('com.docker.compose.project')!=expected_project or labels.get('com.docker.compose.service')!='main' or not c.get('running'):continue
        if any(m.get('Destination')=='/logs/agent' and Path(m.get('Source','')).resolve()==(trial/'agent').resolve() for m in c.get('mounts',[])):matches.append(c)
    return matches[0] if len(matches)==1 else None

def guard(container,mode,job,trial,solver=None):
    payload={'mode':mode,'job':job,'trial':str(trial),'limit_seconds':LIMIT,'grace_seconds':GRACE,'solver':solver}
    source=(ROOT/'container_guard.mjs').read_text()
    if job.startswith('legacy-kz-') and trial.is_relative_to(CAMPAIGNS[1]/'jobs'):
        source=source.replace('/opt/kz/container-run.mjs','/opt/kz-standalone/standalone-run.mjs').replace('/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','/opt/kz-standalone/solve.py')
    # JS supplied as code; policy is stdin. No key, model prompt or tool output.
    return json.loads(command(['docker','exec','-i','-u','0',container['id'],'/opt/node/bin/node','--input-type=module','-e',source.replace("if(process.argv[1]==='-'||process.argv[1]?.endsWith('container_guard.mjs')){","if(true){")],input=json.dumps(payload)))

def inspect_row(campaign,row,containers,enforce):
    record={k:row.get(k) for k in ('job','task','arm','state','requests','tools','grade','fault','solver_exit') if k in row}
    jobs=(campaign/'jobs').resolve()
    if not row.get('job') or '/' in row['job'] or '..' in row['job']:return dict(record,warning='invalid_job_identity')
    trials=[p for p in (jobs/row['job']).glob('*') if p.is_dir() and (p/'config.json').exists()]
    if len(trials)!=1:return record
    trial=trials[0].resolve()
    if not trial.is_relative_to(jobs):return dict(record,warning='trial_outside_campaign')
    receipt=read(trial/'agent/live/server-timeout.json')
    if receipt:record.update(timeout_receipt=receipt,elapsed_seconds=receipt.get('elapsed_seconds'))
    # Never target preflights, official verifier containers, or a graded task.
    if (trial/'result.json').exists() or (trial/'agent/transport-result.json').exists() or (trial/'agent/live/agent-exit.json').exists():
        if receipt:record['stop_reason']='server_wall_limit_3h'
        try:
            with (trial/'agent/live/shared.jsonl').open() as stream:first=json.loads(stream.readline(16384))
            begin=datetime.datetime.fromisoformat(first['time']).timestamp()
            ending=trial/'agent/live/agent-exit.json'
            if ending.exists():record.update(elapsed_seconds=max(0,ending.stat().st_mtime-begin),clock='accounting_start_to_solver_exit')
        except (OSError,ValueError,KeyError,TypeError):pass
        return record
    c=matching_container(containers,trial)
    if c is None:return dict(record,watch_state='waiting_for_solver_container')
    record['container']=c['name'];record['trial']=str(trial)
    try:
        view=guard(c,'probe',row['job'],trial)
        record.update(watch_state=view['state'],elapsed_seconds=view.get('elapsed_seconds'),solver=view.get('solver'))
        if view.get('reason'):record['watch_warning']=view['reason']
        if view.get('elapsed_seconds') is not None:
            record['solver_started_utc']=datetime.datetime.fromtimestamp(time.time()-view['elapsed_seconds'],datetime.timezone.utc).isoformat()
        record['remaining_seconds']=max(0,LIMIT-view['elapsed_seconds']) if view.get('elapsed_seconds') is not None else None
        pending=(view.get('receipt') or {}).get('state')=='terminating'
        if enforce and (pending or view.get('elapsed_seconds',0)>=LIMIT):
            outcome=guard(c,'enforce',row['job'],trial,view.get('solver'));record['timeout_receipt']=outcome
            record['watch_state']=outcome['state'];record['stop_reason']='server_wall_limit_3h'
            with (ROOT/'actions.jsonl').open('a') as stream:stream.write(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),job=row['job'],trial=str(trial),outcome=outcome))+'\n')
    except Exception as error:record['watch_error']=str(error)
    return record

def tick(enforce=True):
    containers=inventory();campaigns=[]
    for root in CAMPAIGNS:
        summary=read(root/'summary.json');health=read(root/'health.json')
        records=summary.get('results',[])
        # Prefer fresh counters from health while retaining all pending/ended rows.
        fresh={r['job']:r for r in health.get('running',[]) if 'job' in r}
        records=[fresh.get(r.get('job'),r) for r in records]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(lambda r:inspect_row(root,r,containers,enforce),records))
        campaigns.append(dict(campaign=str(root),scheduler_state=health.get('state','unknown'),scheduler_updated=health.get('updated_utc'),
          finished=health.get('finished'),pending=health.get('pending'),rows=rows))
    report=dict(updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),enforcement=enforce,
       limit_seconds=LIMIT,poll_seconds=INTERVAL,term_grace_seconds=GRACE,
       clock='actual solver Linux process elapsed; build and grading excluded',paid_api_calls=0,campaigns=campaigns)
    save('status.json',report);return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    if args.once:print(json.dumps(tick(not args.dry_run),indent=2));return
    with (ROOT/'watchdog.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:tick()
            except Exception as error:save('error.json',dict(time=time.time(),error=str(error)))
            time.sleep(INTERVAL)

if __name__=='__main__':main()
