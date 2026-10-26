import fs from 'node:fs';
import {SemanticPlanner} from './runtime/hld/src/semantic-planner.mjs';
import {configuration} from './runtime/hld/src/policy.mjs';
import {parseRoleOutput} from './runtime/hld/src/roles.mjs';
process.env.KZ_APPWORLD='1';
const cases=JSON.parse(fs.readFileSync(new URL('./planner-replay.json',import.meta.url)));
const results=[];
for(const c of cases) {
  const p=c.payload,planner=new SemanticPlanner(configuration({semanticPlannerEnabled:true}));
  Object.assign(planner.state,{routes:p.routes,active:p.active_route_id,pending:p.trigger,nextRouteId:Number(p.next_route_id.slice(1)),taskModel:p.task_model,archive:p.recent_evictions??[]});
  const supplied=Object.fromEntries([...(p.known_evidence_ids??[]),...Object.keys(p.control_events??{})].map(id=>[id,{}]));
  let error=null;
  try { planner.accept(parseRoleOutput(c.output),supplied,1); } catch(e){error=e.message;}
  results.push({job:c.job,line:c.line,old_status:c.old_status,old_error:c.old_error,new_accepted:!error,new_error:error});
}
const report={responses:results.length,old_accepted:results.filter(x=>x.old_status==='semantic_plan_accepted').length,new_accepted:results.filter(x=>x.new_accepted).length,paid_calls:0,scope:'Historical output protocol replay; no new model responses or benchmark outcomes',results};
fs.writeFileSync(new URL('./planner-replay-result.json',import.meta.url),JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,results:report.results.filter(x=>!x.new_accepted)},null,2));
