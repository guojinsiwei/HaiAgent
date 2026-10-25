// Replay observed receipts only up to first changed decision. No tools/models execute.
import fs from 'node:fs';
import {Policy} from '../../projects/kz-dsh/src/policy.mjs';
const raw=JSON.parse(fs.readFileSync(new URL('raw.json',import.meta.url),'utf8').replace(/^\uFEFF/,''));
const results=[];
for(const run of raw.rows.filter(r=>r.arm==='kz-dsh')) {
 const p=new Policy(), ids=new Map();let first=null;
 for(const e of run.events) {
  if(e.event==='tool_admitted') {
   const observed=run.events.find(x=>x.event==='outcome'&&x.callId===e.callId)?.evidence;
   const call={name:e.name,callId:e.callId,arguments:observed?.arguments??{}};
   p.noteAction(call);p.executionStep(call.callId);
  }
  if(e.event==='outcome'&&e.evidence) {
   const r=e.evidence,call={name:r.tool,callId:r.callId,arguments:r.arguments};
   const record=p.observe(call,r,r.before,r.after,r.dependenciesAfter??{});
   if(record)ids.set(record.id,r.id);
   if(p.state.active) {first={at:r.id,line:e.line,trigger:p.state.episode.trigger,
    historicalEvidence:p.state.episode.trigger.evidence.map(id=>ids.get(id))};break;}
  }
 }
 results.push({arm:run.arm,task:run.task,oldEpisodes:run.state?.episode?.serial??0,first});
}
fs.writeFileSync(new URL('replay-dsh.json',import.meta.url),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results));
