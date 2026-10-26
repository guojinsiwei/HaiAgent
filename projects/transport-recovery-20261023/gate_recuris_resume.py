from pathlib import Path
import subprocess,json,hashlib
R=Path(__file__).resolve().parent;O=R/'lhtb';B=O/'bundle'
def once(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def write(p,s):p.unlink();p.write_text(s)
p=B/'dsh-baselines/src/plugin.mjs';s=p.read_text()
s=once(s,'let replayReplies=null,resumePending=!!resume;', 'let replayReplies=null,resumePending=!!resume,resumeReady=null;')
s=once(s,"  ctx.effect(()=>()=>worker?.close());", """  async function ensureResume(){
    if(!resumePending)return;
    if(!worker)throw Error('Resume worker not bound');
    resumeReady??=replayResume(resume,worker,v=>{replayReplies=v;}).then(()=>{resumePending=false;audit('resume_restored',{operations:resume.operations.length,modelCalls:0});});
    await resumeReady;
  }
  ctx.effect(()=>()=>worker?.close());""")
s=once(s,"  ctx.on('llm/stream',async function*(options,next){\n    wall();", "  ctx.on('llm/stream',async function*(options,next){\n    await ensureResume();\n    wall();")
s=once(s,"    if(resumePending){await replayResume(resume,worker,v=>{replayReplies=v;});resumePending=false;audit('resume_restored',{operations:resume.operations.length,modelCalls:0});}", "    await ensureResume();")
write(p,s)
p=B/'dsh-baselines/src/bridge.mjs';s=p.read_text();s=once(s,"    this.child.stderr.on('data'", "    this.child.stdin.on('error',e=>this.fail(e));\n    this.child.stderr.on('data'");write(p,s)
subprocess.run([str(B/'node/bin/node'),'--check',str(B/'dsh-baselines/src/plugin.mjs')],check=True)
subprocess.run(['tar','-czf',str(O/'runtime-final.tar.gz'),'-C',str(B),'node','kz','recuris-dsh','dsh-baselines'],check=True)
p=O/'ready.json';d=json.loads(p.read_text())
for n in d['files']:
    with (O/n).open('rb') as f:d['files'][n]=hashlib.file_digest(f,'sha256').hexdigest()
p.write_text(json.dumps(d,indent=2));print('Resume gate before all model calls installed')
