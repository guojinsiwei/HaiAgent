from pathlib import Path
import shutil,tarfile

ROOT=Path(__file__).resolve().parent
with tarfile.open(ROOT/'runtime-for-repair.tar.gz') as archive:
    archive.extractall(ROOT/'runtime',filter='data')
def replace(path,old,new):
    text=path.read_text(encoding='utf-8')
    assert old in text,(path,old[:90])
    path.write_text(text.replace(old,new),encoding='utf-8')

for arm in ['hld','kzdsh-new']:
    src=ROOT/'runtime'/arm/'src'
    shutil.copyfile(ROOT/'appworld-review.mjs',src/'appworld-review.mjs')
    replace(src/'verification-identity.mjs',"  let command=args.command,cwd=args.workdir??'.';",
        "  args={...args};delete args.description; // Metadata cannot change execution identity.\n  let command=args.command,cwd=args.workdir??'.';")
    p=src/'full-integration.mjs'
    replace(p,"import { CriticCache }", "import {worldControl,reviewEvidence,APPWORLD_REVIEW_RULES} from './appworld-review.mjs';\nimport { CriticCache }")
    replace(p,"    try { return await ctx.tools.execute({name:'bash',arguments:args,callId,agent:entry.agent,signal}); }\n    finally { internalCalls.delete(callId); }",
        "    let prior=null;\n    try {\n      if(role==='critic-check')prior=await worldControl(true);\n      return await ctx.tools.execute({name:'bash',arguments:args,callId,agent:entry.agent,signal});\n    } finally { internalCalls.delete(callId);if(prior)await worldControl(false); }")
    replace(p,"return askRole(ctx,entry,name,system,payload,signal,record,auxiliarySessions);",
        "return askRole(ctx,entry,name,system+(process.env.KZ_APPWORLD==='1'?'\\n'+APPWORLD_REVIEW_RULES:''),payload,signal,record,auxiliarySessions);")
    # Expose real command arguments independently from lossy panel rendering.
    replace(p,"        existing_gaps:ledger.open(),instruction:","        exact_commands:reviewEvidence(s),existing_gaps:ledger.open(),instruction:")
    replace(p,"        if(!preflight.ok&&!ledger.open().length)ledger.registerReview({gaps:['Proposed verification is not executable or attributable.'],next_step:preflight.errors.join('; ')},s.taskGoal);", """        if(!preflight.ok) {
          s.critic.lastError=preflight.errors.join('; ');
          record(e,'critic_protocol_error',{errors:preflight.errors,attempt,application_gap_created:false});
          if(attempt===0)continue; // One bounded format repair; never manufacture a task defect.
        }""")
    replace(p,"    const startToken=token();", """    const startToken=token();
    const world=await worldControl();
    if(world) {
      const progress=JSON.stringify([world.revision,world.submitted]);
      s.appworldReview= s.appworldReview?.progress===progress?s.appworldReview:{progress,rounds:0};
      if(s.appworldReview.rounds>=3) {
        ledger.state.status='incomplete_review_stalled';
        record(e,'completion_incomplete',{reason:'three_reviews_without_application_state_progress',officialSuccess:null});
        return; // Bound control overhead without claiming success or erasing gaps.
      }
      s.appworldReview.rounds++;
    }""")
    # Complete schema at the beginning, where the model reads its example.
    p=src/'roles.mjs'
    replace(p,'"stdout_contains":["expected public marker"]}]}',
        '"stdout_contains":["expected public marker"],"gap_ids":[],"requirement_quotes":["exact public task substring"],"provenance":{"author":"critic","kind":"independent_derivation","expected_rule":"actual rule to assert","sources":[{"kind":"task","quote":"exact public task substring"}],"independence":"derive expected values from public inputs and task rules","derivation":"explicit derivation from source to expected result"}}]}')
    replace(p,'checks:[] never proves success.',
        'At plan_checks stage an accept with checks:[] is invalid; provide a real read-only check with its complete schema. Do not send verdict-stage output prematurely. checks:[] never proves success.')
    # Strict JSON with recoverable surrounding explanation; never repair data.
    replace(p,"  const value=JSON.parse(text);", """  let value;
  try { value=JSON.parse(text); }
  catch(original) {
    const start=text.indexOf('{');let depth=0,quoted=false,escaped=false,end=-1;
    for(let i=start;i>=0&&i<text.length;i++) {
      const c=text[i];if(quoted){if(escaped)escaped=false;else if(c==='\\\\')escaped=true;else if(c==='\"')quoted=false;continue;}
      if(c==='\"')quoted=true;else if(c==='{')depth++;else if(c==='}'&&--depth===0){end=i+1;break;}
    }
    if(start<0||end<0||/[{}]/u.test(text.slice(end)))throw original;
    value=JSON.parse(text.slice(start,end));
  }""")

# HLD retains strict old protocol for non-AppWorld deployments. AppWorld V2
# separates registry bookkeeping from the model's semantic decisions.
src=ROOT/'runtime/hld/src'
p=src/'semantic-planner.mjs'
replace(p,"  const [kind, executable, args] = commandIdentity(call.arguments?.command ?? '');", """  const [kind, executable, args] = commandIdentity(call.arguments?.command ?? '');
  if(process.env.KZ_APPWORLD==='1'&&kind==='literal'&&/^(?:python|python3)$/u.test(executable)&&
    args[0]==='/opt/experiment/client.py'&&args.includes('--read-only')&&args.includes('--file')&&
    args.length===4&&args[args.indexOf('--file')+1]?.startsWith('/app/'))return true;""")
replace(p,"    const s = this.state, old = this.active(), available = new Set(Object.keys(supplied));", """    const s = this.state, old = this.active(), available = new Set(Object.keys(supplied));
    if(process.env.KZ_APPWORLD==='1')answer=normalizePlan(answer,s);""")
replace(p,"clock - s.lastAttemptClock >= this.config.semanticPlannerCooldown", "clock - s.lastAttemptClock >= this.config.semanticPlannerCooldown*Math.min(8,2**(s.protocolFailures??0))")
replace(p,"    const s = this.state; s.lastError = reason;", "    const s = this.state; s.lastError = reason;s.protocolFailures=(s.protocolFailures??0)+1;")
replace(p,"s.revision++; s.lastError = null;", "s.revision++; s.lastError = null;s.protocolFailures=0;")
p.write_text(p.read_text(encoding='utf-8')+'''

export const SEMANTIC_V2 = `Protocol V2: return new_routes only, with temporary ids N1 and optionally N2.
Do not copy retained routes into new_routes. The harness allocates stable IDs.
Evaluate every retained route by its D ID and every new route by its N ID.
All other route fields (hypothesis, mechanism, target, steps[2..8], progress_signal, abandon_when, evidence_ids) remain required.
The harness selects the highest-scored eligible route. If a switch is appropriate, give contrast:{dimension:"hypothesis|mechanism|target",reason:"substantive changed premise"}; it resolves the exact axis strings from the immutable registry.
Cite known_evidence_ids only; use [] when no supporting observation exists. Details can be retrieved from the task archive. Never infer evidence contents from an ID.
Prior failure diagnostics are provided. Repair those fields, do not repeat the entire state snapshot as an answer.`;

export function normalizePlan(value,state) {
  if(!value||typeof value!=='object')return value;
  const a=structuredClone(value),existing=new Set(state.routes.map(r=>r.id));
  const incoming=a.new_routes??a.routes;
  if(!Array.isArray(incoming))return a;
  // Legacy output may repeat retained definitions. Ignore those copies; they
  // never overwrite the registry or become fabricated new directions.
  const fresh=incoming.filter(r=>!existing.has(r?.id));
  const remap=new Map();
  a.routes=fresh.map((r,i)=>{const id=`D${state.nextRouteId+i}`;remap.set(r.id??`N${i+1}`,id);return {...r,id};});
  if(Array.isArray(a.evaluations))a.evaluations=a.evaluations.map(e=>({...e,route_id:remap.get(e.route_id)??e.route_id}));
  const candidates=[...state.routes,...a.routes],loop=state.pending&&!['initial','route_window'].includes(state.pending.kind);
  const eligible=(a.evaluations??[]).filter(e=>e.disposition==='retain'&&Number.isFinite(e.suitability)&&
    candidates.some(r=>r.id===e.route_id&&(!r.status||['ready','active'].includes(r.status)))&&!(loop&&e.route_id===state.active));
  eligible.sort((x,y)=>y.suitability-x.suitability);
  if(eligible.length)a.selected_route_id=eligible[0].route_id;
  const old=state.routes.find(r=>r.id===state.active),next=candidates.find(r=>r.id===a.selected_route_id);
  if(old&&next&&old.id!==next.id&&a.contrast&&axes.includes(a.contrast.dimension)) {
    a.contrast.previous=old[a.contrast.dimension];a.contrast.next=next[a.contrast.dimension];
  }
  return a;
}
''',encoding='utf-8')
p=src/'full-integration.mjs'
replace(p,"SEMANTIC_PLANNER }", "SEMANTIC_PLANNER, SEMANTIC_V2 }")
replace(p,"const answer=await role(e,'semantic_planner',SEMANTIC_PLANNER,", "const answer=await role(e,'semantic_planner',SEMANTIC_PLANNER+(process.env.KZ_APPWORLD==='1'?'\\n'+SEMANTIC_V2:''),")
replace(p,"        next_route_id:","        previous_error:planner.state.lastError,known_evidence_ids:Object.keys(s.evidence),next_route_id:")
replace(p,"planner.accept(answer,{...evidence,...controls},clock);", "planner.accept(answer,{...s.evidence,...controls},clock);")
replace(p,"    planner.started(clock);", "    if(process.env.KZ_APPWORLD==='1'&&(await worldControl())?.submitted)return;\n    planner.started(clock);")
p=ROOT/'runtime/hld/.runtime/kz.patch.yml'
replace(p,'semanticReconnaissanceSteps: 8','semanticReconnaissanceSteps: 3')
(ROOT/'runtime/hld/config/kz.patch.yml').write_text(p.read_text(encoding='utf-8').replace('"/opt/kz/src/plugin.mjs"','__KZ_PLUGIN_PATH__').replace('shellReceipts: true','shellReceipts: false'),encoding='utf-8')

# New adapter is versioned, leaving the original server and client immutable.
server=(ROOT.parent/'world_server.py').read_text(encoding='utf-8')
server=server.replace('from appworld import AppWorld','from appworld import AppWorld\nfrom appworld_guard import AppWorldGuard,collect_pages\nfrom appworld.requester import Requester')
server=server.replace("world.execute('pass')",'''world.execute('pass')
docs={p.stem:json.loads(p.read_text()) for p in Path('/appworld/data/api_docs/standard').glob('*.json')}
guard=AppWorldGuard(world.task.instruction,docs)
original_request=Requester._request
def guarded_request(self,_app_name,_api_name,**kwargs):
    return guard.invoke(lambda **data:original_request(self,**data),_app_name,_api_name,**kwargs)
Requester._request=guarded_request
world.shell.user_ns['collect_pages']=collect_pages
''')
server=server.replace("'ground_truth_loaded':False", "'ground_truth_loaded':False,'guard':guard.status()")
server=server.replace("        if self.path!='/execute':self.send_error(404);return", """        if self.path=='/review-mode':
            q=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            if type(q.get('read_only')) is not bool:self.send_error(400);return
            guard.read_only=q['read_only'];self.reply({'guard':guard.status()});return
        if self.path!='/execute':self.send_error(404);return""")
server=server.replace("        try:\n            result=world.execute(code)","        prior=guard.read_only;guard.read_only=prior or q.get('read_only') is True;guard.events=[]\n        try:\n            result=world.execute(code)")
server=server.replace("'interactions':world.num_interactions", "'interactions':world.num_interactions,'guard':guard.status(),'guard_events':guard.events[-20:]")
server=server.replace("print('WORLD_READY'", "        finally:guard.read_only=prior\nprint('WORLD_READY'")
(ROOT/'world_server.py').write_text(server,encoding='utf-8')
print('Built versioned repair runtime; no deployment modified.')
