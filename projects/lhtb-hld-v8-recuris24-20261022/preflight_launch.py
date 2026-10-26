"""Check live production entry gates and original graders, then launch once."""
from pathlib import Path
import ast,hashlib,json,os,subprocess,sys,tempfile,time,uuid
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def save(n,v):(ROOT/n).write_text(json.dumps(v,indent=2))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    from spending import Ledger,BudgetError
    from campaign import run_trial
    profile=read(ROOT/'budget-profile.json')
    assert profile['task_limit_microcny']==24000000 and profile['campaign_limit_microcny']==1152000000 and len(profile['jobs'])==48
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        ledger=Ledger(Path(directory)/'ledger.sqlite',profile)
        req=dict(id='first',job=profile['jobs'][0],arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=32768)
        assert ledger.reserve(req)['reserved_microcny']==518144
        ledger.settle(dict(id='first',tokens=0))
        try:ledger.reserve({**req,'job':'unrelated-campaign','id':'invalid'})
        except BudgetError as e:assert e.reason=='job_not_authorized'
        else:raise AssertionError('Job allowlist missing')
        with ledger.db() as db:db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent',req['job'],'kz',23900000,23900000,'settled',time.time()))
        try:ledger.reserve({**req,'id':'over24'})
        except BudgetError as e:assert e.reason=='per_task_budget_exhausted'
        else:raise AssertionError('Task cap missing')
        with ledger.db() as db:
            db.execute('DELETE FROM calls');db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent','other','kz',1151900000,1151900000,'settled',time.time()))
        try:ledger.reserve({**req,'id':'over1152'})
        except BudgetError as e:assert e.reason=='campaign_budget_exhausted'
        else:raise AssertionError('Campaign cap missing')
    shared=(ROOT/'bundle/kz/shared-budget.mjs').read_text()
    assert "existsSync(dir+'/shared-state.json')" in shared and 'state.requests>=800' in shared and 'state.tools>=600' in shared
    # A mocked real plugin lifecycle proves counters persist across two separate phases.
    script="""import fs from 'node:fs';import {apply} from './bundle/kz/shared-budget.mjs';
const dir=process.env.PAIRED_AUDIT_DIR;const handlers={};const ctx={on:(event,fn)=>{handlers[event]=fn}};
apply(ctx);let tool=handlers['tools/execute'];await tool({name:'probe',callId:'1'},async()=>({}));
apply(ctx);tool=handlers['tools/execute'];await tool({name:'probe',callId:'2'},async()=>({}));
if(JSON.parse(fs.readFileSync(dir+'/shared-state.json')).tools!==2)throw Error('Phase counter reset');
console.log('Cross-phase tool accounting OK; zero model calls');"""
    (ROOT/'phase-preflight.mjs').write_text(script)
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        subprocess.run([str(ROOT/'bundle/node/bin/node'),str(ROOT/'phase-preflight.mjs')],cwd=ROOT,env={**os.environ,'PAIRED_AUDIT_DIR':directory},check=True)
    trial_source=(ROOT/'vendor-src/harbor/trial/trial.py').read_text()
    tree=ast.parse(trial_source)
    hide=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_hide_shared_verifier_artifacts')
    assert 'operator-verifier-phases' in ast.get_source_segment(trial_source,hide)
    results=[]
    for arm in ['hld','recuris']:
        save('preflight-health.json',dict(state='production_entry_and_official_grader',arm=arm,model_calls=0,updated=time.time()))
        os.environ['ENTRY_ACCEPTANCE']='1'
        os.environ['ENTRY_CONTINUATION_TEST']='1'
        row=dict(task='chess-mate',arm=arm,job='entry-'+arm+'-'+uuid.uuid4().hex[:8])
        result=run_trial(row,True);results.append(dict(arm=arm,**result))
        assert result['engineering_clean'] and result['harbor_exit']==0,result
        assert result['continuation'].get('continuation_isolation_verified') and result['continuation'].get('continue_until_timeout_phases')==1,result
    os.environ.pop('ENTRY_ACCEPTANCE',None)
    os.environ.pop('ENTRY_CONTINUATION_TEST',None)
    save('acceptance.json',dict(passed=True,model_calls=0,checks=results,cross_phase_counters_verified=True))
    files={str(p.relative_to(ROOT)):sha(p) for p in ROOT.iterdir() if p.is_file() and (p.suffix in ['.py','.mjs'] or p.name in ['protocol.json','selection.json','tasks.json','budget-profile.json','runtime-final.tar.gz','python-runtime.tar.gz','queue.json'])}
    files.update({str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'vendor-src/harbor').rglob('*.py')})
    save('ready.json',dict(passed=True,model_calls=0,files=files))
    save('validation.json',dict(passed=True,model_calls=0,tasks=24,trials=48,campaign_cny=1152,per_run_cny=24,acceptance=results))
    (ROOT/'PAID_START_HOLD').unlink(missing_ok=True)
    subprocess.run([sys.executable,str(ROOT/'campaign.py')],check=True)
    save('preflight-health.json',dict(state='launched',updated=time.time(),paid_preflight_calls=0))
if __name__=='__main__':
    try:main()
    except Exception as error:
        save('preflight-health.json',dict(state='failed_no_paid_launch',error_type=type(error).__name__,error=str(error)[:1800],updated=time.time()));raise
