import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {SemanticPlanner as Before} from './analysis/bundle/kz/src/semantic-planner.mjs';
import {SemanticPlanner as After} from './candidate/src/semantic-planner.mjs';
import {clip as oldClip} from './analysis/bundle/kz/src/terminal.mjs';
import {clip as newClip} from './candidate/src/terminal.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
process.env.HLD_PLANNER_PROTOCOL='3';
const results=[],projections=[];
for(const index of [5,8,11,12,10]) {
 const dir=path.join(root,`analysis/jobs/swp-${String(index).padStart(2,'0')}-hld/live/kz`);
 const journal=fs.readdirSync(dir).find(f=>f.endsWith('.jsonl'));
 const events=fs.readFileSync(path.join(dir,journal),'utf8').trim().split('\n').map(JSON.parse);
 for(let i=0;i<events.length;i++)if(events[i].event==='role_request'&&events[i].role==='semantic_planner') {
  const req=events[i],response=events.slice(i+1).find(e=>e.event==='role_response'&&e.sessionId===req.sessionId);
  if(!response)continue;
  let answer;try{answer=JSON.parse(response.output);}catch{continue;}
  const p=req.payload;
  const run=Class=>{
   const q=new Class({semanticPlannerEnabled:true,explorationEnabled:true,semanticMaxRoutes:p.route_window_capacity});
   Object.assign(q.state,{routes:structuredClone(p.routes),active:p.active_route_id,pending:p.trigger,
    nextRouteId:Number(p.next_route_id.slice(1)),phase:p.active_route_id?'solving':'planning'});
   const supplied=Object.fromEntries([...p.known_evidence_ids,...Object.keys(p.control_events??{})].map(id=>[id,{id}]));
   try{q.accept(answer,supplied,req.hostSeq??0);return {accepted:true,route:q.state.active};}catch(e){return {accepted:false,error:e.message};}
  };
  results.push({index,request:req.sessionId,before:run(Before),after:run(After)});
 }
 const state=JSON.parse(fs.readFileSync(path.join(dir,fs.readdirSync(dir).find(f=>f.endsWith('.json'))),'utf8')).full;
 for(const gap of state.completion?.gaps??[]) {
  let oldError=null;try{oldClip(gap.next_step,300);}catch(e){oldError=e.message;}
  const rendered=newClip(gap.next_step,300);
  projections.push({index,gap:gap.id,before_error:oldError,after_length:rendered.length});
 }
}
const summary={plans:results.length,before_accepted:results.filter(x=>x.before.accepted).length,
 after_accepted:results.filter(x=>x.after.accepted).length,
 recovered:results.filter(x=>!x.before.accepted&&x.after.accepted).length,
 regressions:results.filter(x=>x.before.accepted&&!x.after.accepted).length,
 structured_followup_crashes_recovered:projections.filter(x=>x.before_error).length,
 note:'Offline protocol replay of frozen responses, not new model execution or task success.'};
fs.writeFileSync(path.join(root,'offline-replay.json'),JSON.stringify({summary,results,projections},null,2));
console.log(summary);
if(summary.regressions)process.exitCode=1;
