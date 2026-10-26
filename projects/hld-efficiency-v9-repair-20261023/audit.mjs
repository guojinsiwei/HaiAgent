import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {parseRoleOutput} from './candidate/src/roles.mjs';
import {plannerRouteView} from './candidate/src/efficiency.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const fixtures=JSON.parse(fs.readFileSync(path.join(root,'validation/planner-fixtures.json')));
const totals={};let projectionBefore=0,projectionAfter=0;
for(const f of fixtures) {
  const arm=f.root.includes('v9')?'v9':'v8';const t=totals[arm]??={calls:0,accepted:0,failed:0,errors:{}};
  t.calls++;t[f.outcome==='semantic_plan_accepted'?'accepted':'failed']++;
  if(f.outcome==='semantic_plan_failed')t.errors[f.error]=(t.errors[f.error]??0)+1;
  if(arm==='v9') {
    projectionBefore+=JSON.stringify(f.payload.routes??[]).length;
    projectionAfter+=JSON.stringify((f.payload.routes??[]).map(plannerRouteView)).length;
  }
}
const files=dir=>fs.readdirSync(dir,{withFileTypes:true}).filter(x=>x.name!=='node_modules'&&x.name!=='.runtime').flatMap(x=>x.isDirectory()?files(path.join(dir,x.name)):[path.join(dir,x.name)]);
const hashes=dir=>Object.fromEntries(files(dir).map(f=>[path.relative(dir,f).replaceAll('\\','/'),crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')]));
const before=hashes(path.join(root,'frozen-v9')),after=hashes(path.join(root,'candidate'));
const original=hashes(path.join(root,'../hld-efficiency-v9-20261022/candidate'));
const originalChanges=Object.keys(before).filter(k=>before[k]!==original[k]);
if(originalChanges.length)throw new Error('Original v9 changed: '+originalChanges.join(','));
const diagnostics=[];
for(const f of fixtures.filter(x=>x.root.includes('v9')&&x.outcome==='semantic_plan_failed')) {
  try {
    const a=parseRoleOutput(f.output),issues=[];
    for(const [i,r] of (a.new_routes??[]).entries())for(const k of ['hypothesis','mechanism','target','progress_signal','abandon_when'])if(typeof r[k]!=='string'||!r[k].trim())issues.push(`new_routes[${i}].${k}`);
    diagnostics.push({task:f.task,error:f.error,missingFields:issues});
  }catch(e){diagnostics.push({task:f.task,error:f.error,parseError:e.message});}
}
const report={paid_model_calls:0,fixture_count:fixtures.length,planner:totals,
  route_registry_display_projection:{before_chars:projectionBefore,after_chars:projectionAfter,reduction_fraction:1-projectionAfter/projectionBefore,note:'Offline projection only; excludes other payload fields and does not estimate actual cost.'},
  historical_seven_clean_pairs:{v8:{requests:1222,settled_cny:44.356860,passed:0},v9:{requests:1569,settled_cny:46.369115,passed:0},note:'Historical unpaired timing; request counters include rejected requests. Not a successful-task efficiency estimate.'},
  originalChanges,changedFiles:Object.keys(after).filter(k=>before[k]!==after[k]),sourceHashes:after,diagnostics};
fs.writeFileSync(path.join(root,'validation/audit.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,sourceHashes:undefined,diagnostics:undefined},null,2));
