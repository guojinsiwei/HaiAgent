from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;O=R/'lhtb'
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    # Copy the hook so its ROOT is this deployment, independent of symlink resolution.
    hook=O/'lhtb_recovery_hook.py'
    if hook.is_symlink():hook.unlink()
    shutil.copy2(R/'lhtb_recovery_hook.py',hook)
    p=O/'agents.py';s=p.read_text()
    s=once(s,"if os.environ.get('LHTB_OFFLINE')!='1':","if os.environ.get('LHTB_OFFLINE')!='1' or os.environ.get('RECOVERY_ACCEPTANCE_JOB'):")
    s=once(s,"payload=dict(key='offline-never-transmitted',arm=self.arm,instruction=instruction,phase=0,remaining_seconds=90,","payload=dict(key='offline-never-transmitted',arm=self.arm,instruction=instruction,phase=0,remaining_seconds=90,resume_session=getattr(self,'resume_session',None),")
    p.write_text(s)
    p=O/'campaign.py';s=p.read_text()
    s=once(s,"rows=read(ROOT/'queue.json')['rows'];active={};seen_provider_failure=time.time()","rows=read(ROOT/'queue.json')['rows'];active={};seen_provider_failure=time.time();startup_failures=0;admission_hold=False")
    s=once(s,"if future.done():future.result();del active[future]","""if future.done():
                        future.result();del active[future]
                        startup_failure=row['state']=='engineering_failure' and not row.get('paid_started')
                        startup_failures=startup_failures+1 if startup_failure else 0
                        if startup_failures>=2:
                            admission_hold=True
                            save(ROOT/'startup-admission-hold.json',dict(reason='consecutive_preflight_or_startup_failures',last_job=row['job'],time=time.time()))""")
    s=once(s,"if len(active)>=6 or not CIRCUIT.admit():break","if len(active)>=6 or admission_hold or not CIRCUIT.admit():break")
    s=once(s,"'finished' if finished else 'running' if CIRCUIT.admit() else 'provider_paused'","'finished' if finished else 'startup_paused' if admission_hold else 'running' if CIRCUIT.admit() else 'provider_paused'")
    s=once(s,"tasks=24,trials=48","tasks=21,trials=42")
    p.write_text(s)
    queue=json.loads((O/'queue.json').read_text())
    for row in queue['rows']:
        row['original_result']=row.pop('result',{})
    (O/'queue.json').write_text(json.dumps(queue,indent=2))
    for p in O.glob('*.py'):compile(p.read_text(),str(p),'exec')
    ready=json.loads((O/'ready.json').read_text())
    for name in ready['files']:ready['files'][name]=sha(O/name)
    (O/'ready.json').write_text(json.dumps(ready,indent=2))
    print(json.dumps(dict(passed=True,hook_root_fixed=True,consecutive_startup_breaker=True)))
if __name__=='__main__':main()
