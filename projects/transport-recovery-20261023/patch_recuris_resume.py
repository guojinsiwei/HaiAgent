from pathlib import Path
import json,shutil,subprocess,hashlib
R=Path(__file__).resolve().parent;O=R/'lhtb';B=O/'bundle';P=R.parent/'lhtb-hld-v8-recuris24-20261022/bundle'
def replace(p,s):
    if p.exists():p.unlink()
    p.write_text(s)
def once(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
p=B/'dsh-baselines/src/plugin.mjs';s=(P/'dsh-baselines/src/plugin.mjs').read_text()
s="import {loadResume,replayResume} from './recuris-resume.mjs';\n"+s
s=once(s,"  if(existsSync(marker))throw new Error('Fresh per-task audit directory required; implicit memory resume forbidden');", "  const resume=loadResume(c);\n  if(existsSync(marker)&&!resume)throw new Error('Fresh per-task audit directory required; implicit memory resume forbidden');")
s=once(s,'  writeFileSync(marker,JSON.stringify({...c,worker:c.worker?.href},null,2));','  if(!resume)writeFileSync(marker,JSON.stringify({...c,worker:c.worker?.href},null,2));')
s=once(s,"  let agent=null, worker=null, signal=null, roleSerial=0, evidenceSerial=0, pendingFeedback=null;", """  let replayReplies=null,resumePending=!!resume;
  if(resume){Object.assign(state,resume.state);state.recoveryHistoricalFaults=state.faults;state.faults=[];state.status='running';}
  state.bootstrap_pid=process.pid;
  let agent=null, worker=null, signal=null, roleSerial=resume?.roleSerial??0, evidenceSerial=resume?.evidenceSerial??0, pendingFeedback=null;""")
s=once(s,'  async function ask(m) {',"""  async function ask(m) {
    if(replayReplies!==null){const reply=replayReplies.shift();if(!reply||reply.role!==m.role)throw Error('Missing original role response during offline resume');return {text:reply.text,usage:{}};}""")
s=once(s,'    agent=a;state.session=a.session.id;',"    if(resume&&resume.state.session!==a.session.id)throw Error('Resumed agent session differs');\n    agent=a;state.session=a.session.id;")
s=once(s,"    if(!state.initialized){state.panel=await call('init'", "    if(resumePending){await replayResume(resume,worker,v=>{replayReplies=v;});resumePending=false;audit('resume_restored',{operations:resume.operations.length,modelCalls:0});}\n    if(!state.initialized){state.panel=await call('init'")
replace(p,s);shutil.copy2(R/'recuris-resume.mjs',B/'dsh-baselines/src/recuris-resume.mjs')
p=B/'kz/container-run.mjs';s=p.read_text();s=once(s,'const config={instruction:bundle.instruction,','const config={resumeSession:bundle.resume_session??null,instruction:bundle.instruction,');replace(p,s)
p=B/'kz/boot-guard.mjs';s=p.read_text();s=once(s,"if(state.algorithm!=='recuris'||!state.session)","if(state.algorithm!=='recuris'||!state.session||state.bootstrap_pid!==process.pid)");replace(p,s)
p=O/'agents.py';s=p.read_text();needle="                    assert ledger.status()['settled_microcny']==ledger.status()['reserved_microcny']==0"
s=once(s,needle,needle+"\n                    errorlog=self.logs_dir/f'phase-{getattr(self,\"recovery_initial_phase\",0):04d}/dsh.stderr.log'\n                    assert not errorlog.exists() or not errorlog.read_text().strip(), 'Algorithm bootstrap warnings during acceptance'\n                    if self.arm=='recuris' and getattr(self,'resume_session',None):\n                        audit=self.logs_dir/f'phase-{getattr(self,\"recovery_initial_phase\",0):04d}/recuris/events.jsonl'\n                        assert any(json.loads(line).get('event')=='resume_restored' for line in audit.read_text().splitlines()), 'Recuris mechanisms did not resume'")
p.write_text(s)
for p in [B/'dsh-baselines/src/plugin.mjs',B/'kz/container-run.mjs',B/'kz/boot-guard.mjs']:subprocess.run([str(B/'node/bin/node'),'--check',str(p)],check=True)
subprocess.run(['tar','-czf',str(O/'runtime-final.tar.gz'),'-C',str(B),'node','kz','recuris-dsh','dsh-baselines'],check=True)
p=O/'ready.json';d=json.loads(p.read_text())
for n in d['files']:
    with (O/n).open('rb') as f:d['files'][n]=hashlib.file_digest(f,'sha256').hexdigest()
d['engineering_resume_patch']='Explicit same-session Recuris restore; historical worker operations replayed with saved role replies; worker algorithm unmodified.'
p.write_text(json.dumps(d,indent=2));print('Recuris explicit resume deployed')
