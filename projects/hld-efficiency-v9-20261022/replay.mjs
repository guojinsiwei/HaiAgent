// Read-only replay of historical payloads. No provider, credentials or benchmark
// runner is imported. Character savings are not measured token/currency savings.
import {readFile,writeFile,readdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {criticView,contextDelta,roleOutputLimit} from './candidate/src/efficiency.mjs';
const root=fileURLToPath(new URL('./',import.meta.url));
const evidence=path.resolve(root,'../../reports/hld-ab-attribution-20261022/evidence');
const output={kind:'historical_payload_projection_only',modelCalls:0,items:[],limitations:[
  'Only historical Critic plan panels are available here; these are not a replay of every pre-step context.',
  'New model behavior, actual tokens, currency, success rates and wall time require a paired experiment.',
  'Output limits are ceilings. A smaller ceiling alone does not demonstrate lower realized cost.'
]};
for(const task of (await readdir(evidence,{withFileTypes:true})).filter(x=>x.isDirectory()).map(x=>x.name)) {
  const file=path.join(evidence,task,'hld-new','events.json');
  let events;try{events=JSON.parse(await readFile(file,'utf8'));}catch{continue;}
  let prior=null;
  const row={task,criticPanels:0,originalPanelChars:0,compactPanelChars:0,betweenPanelTransitions:0,transitionFullChars:0,transitionDeltaChars:0,roleRequests:[]};
  for(const e of events.filter(x=>x.event==='role_request')) {
    row.roleRequests.push({role:e.role,stage:e.payload.stage??null,originalLimit:e.route?.maxTokens??null,candidateInitialLimit:roleOutputLimit(e.role,e.payload,e.route??{},{}),inputChars:e.system.length+JSON.stringify(e.payload).length});
    const panel=e.payload?.panel;if(!panel?.error_routes?.critic)continue;
    const next=structuredClone(panel);next.error_routes.critic=criticView(next.error_routes.critic);
    row.criticPanels++;row.originalPanelChars+=JSON.stringify(panel).length;row.compactPanelChars+=JSON.stringify(next).length;
    if(prior){row.betweenPanelTransitions++;row.transitionFullChars+=JSON.stringify(next).length;row.transitionDeltaChars+=(contextDelta(prior,next)??'').length;}
    prior=next;
  }
  output.items.push(row);
}
output.aggregate=Object.fromEntries(['criticPanels','originalPanelChars','compactPanelChars','betweenPanelTransitions','transitionFullChars','transitionDeltaChars'].map(k=>[k,output.items.reduce((sum,r)=>sum+r[k],0)]));
await writeFile(path.join(root,'validation/historical-projection.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify(output.aggregate));
